# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import torch
import numpy as np
from semilearn.algorithms.algorithmbase import AlgorithmBase
from semilearn.algorithms.utils import ce_loss, consistency_loss, SSL_Argument


class MeanTeacher(AlgorithmBase):
    """
        MeanTeacher algorithm (https://arxiv.org/abs/1703.01780).

        Args:
        - args (`argparse`):
            algorithm arguments
        - net_builder (`callable`):
            network loading function
        - tb_log (`TBLog`):
            tensorboard logger
        - logger (`logging.Logger`):
            logger to use
        - unsup_warm_up (`float`, *optional*, defaults to 0.4):
            Ramp up for weights for unsupervised loss
    """
    def __init__(self, args, net_builder, tb_log=None, logger=None, **kwargs):
        super().__init__(args, net_builder, tb_log, logger, **kwargs)
        # mean teacher specificed arguments
        self.init(unsup_warm_up=args.unsup_warm_up)
    
    def init(self, unsup_warm_up=0.4):
        self.unsup_warm_up = unsup_warm_up 

    def train_step(self, x_lb, y_lb, x_ulb_w, x_ulb_s):
        # inference and calculate sup/unsup losses
        with self.amp_cm():

            logits_x_lb = self.model(x_lb)

            self.ema.apply_shadow()
            with torch.no_grad():
                self.bn_controller.freeze_bn(self.model)
                logits_x_ulb_w = self.model(x_ulb_w)
                self.bn_controller.unfreeze_bn(self.model)
            self.ema.restore()

            self.bn_controller.freeze_bn(self.model)
            logits_x_ulb_s = self.model(x_ulb_s)
            self.bn_controller.unfreeze_bn(self.model)


            sup_loss = ce_loss(logits_x_lb, y_lb, reduction='mean')
            unsup_loss, _ = consistency_loss(logits_x_ulb_s,
                                             logits_x_ulb_w,
                                             'mse')
            
            unsup_warmup = np.clip(self.it / (self.unsup_warm_up * self.num_train_iter),  a_min=0.0, a_max=1.0)
            total_loss = sup_loss + self.lambda_u * unsup_loss * unsup_warmup

        # parameter updates
        self.parameter_update(total_loss)

        tb_dict = {}
        tb_dict['train/sup_loss'] = sup_loss.item()
        tb_dict['train/unsup_loss'] = unsup_loss.item()
        tb_dict['train/total_loss'] = total_loss.item()
        return tb_dict

    @staticmethod
    def get_argument():
        return [
            SSL_Argument('--unsup_warm_up', float, 0.4, 'warm up ratio for unsupervised loss'),
        ]