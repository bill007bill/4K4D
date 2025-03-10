# Default loss module (called supervisor)
import torch
from torch import nn
from torch.nn import functional as F

from easyvolcap.engine import SUPERVISORS
from easyvolcap.engine.registry import call_from_cfg
from easyvolcap.utils.console_utils import *
from easyvolcap.utils.loss_utils import eikonal, lossfun_zip_outer
from easyvolcap.models.supervisors.volumetric_video_supervisor import VolumetricVideoSupervisor


@SUPERVISORS.register_module()
class GeometrySupervisor(VolumetricVideoSupervisor):
    def __init__(self,
                 network: nn.Module,

                 # SDF model
                 eikonal_loss_weight: float = 0.0,
                 zip_prop_loss_weight: float = 0.0,
                 curvature_loss_weight: float = 0.0,

                 **kwargs,
                 ):
        call_from_cfg(super().__init__, kwargs, network=network)

        self.zip_prop_loss_weight = zip_prop_loss_weight
        self.eikonal_loss_weight = eikonal_loss_weight
        self.curvature_loss_weight = curvature_loss_weight

    def compute_loss(self, output: dotdict, batch: dotdict, loss: torch.Tensor, scalar_stats: dotdict, image_stats: dotdict):
        # Compute the actual loss here
        if self.eikonal_loss_weight > 0.0 and 'gradients' in output:
            gradients = output.gradients
            eikonal_loss = eikonal(gradients)
            scalar_stats.eikonal_loss = eikonal_loss
            loss += self.eikonal_loss_weight * eikonal_loss

        if self.curvature_loss_weight > 0.0 and 'sampled_sdf' in output:
            delta = self.network.finite_diff_delta
            centered_sdf = output.sdf
            sourounding_sdf = output.sampled_sdf
            sourounding_sdf = sourounding_sdf.reshape(centered_sdf.shape[:2] + (3, 2))
            curvature = (sourounding_sdf.sum(dim=-1) - 2 * centered_sdf) / (delta ** 2)
            curvature_loss = curvature.abs().mean() * self.network.curvature_loss_multi_factor
            scalar_stats.curvature_loss = curvature_loss
            loss += self.curvature_loss_weight * curvature_loss

        if 's_vals_prop' in output and 'weights_prop' in output and \
           len(output.s_vals_prop) and len(output.weights_prop) and \
           's_vals' in output and 'weights' in output and \
           self.zip_prop_loss_weight > 0:
            zip_prop_loss = 0
            pulse_width = [0.03, 0.003, 0.0003]
            for i in range(len(output.s_vals_prop)):
                zip_prop_loss += lossfun_zip_outer(
                    output.s_vals.detach(), output.weights.detach(),
                    output.s_vals_prop[i], output.weights_prop[i],
                    pulse_width=pulse_width[i])
            scalar_stats.zip_prop_loss = zip_prop_loss
            loss += self.zip_prop_loss_weight * zip_prop_loss

        return loss
