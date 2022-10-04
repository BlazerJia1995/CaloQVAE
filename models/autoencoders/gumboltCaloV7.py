"""
GumBolt implementation for Calorimeter data - Special model for piplus
V7 - Energy conditioning added to the decoder - Energy conditioning added to the encoder - No hit masking - Compare to V5 with hit masking

Author : Abhi (abhishek@myumanitoba.ca)
"""

# Torch imports
import torch
from torch.nn import ReLU, MSELoss

# DiVAE.models imports
from models.autoencoders.gumbolt import GumBolt
from models.networks.basicCoders import BasicDecoder
from models.networks.hierarchicalEncoder import HierarchicalEncoder

from CaloQVAE import logging
logger = logging.getLogger(__name__)

class GumBoltCaloV7(GumBolt):
    
    def __init__(self, **kwargs):
        super(GumBoltCaloV7, self).__init__(**kwargs)
        self._model_type = "GumBoltCaloV7"
        self._energy_activation_fct = ReLU()
        self._output_loss = MSELoss(reduction="none")
        
    def forward(self, x, is_training):
        """
        - Overrides forward in dvaepp.py
        
        Returns:
            out: output container 
        """
        logger.debug("forward")
        
        #see definition for explanation
        out=self._output_container.clear()
        
	    #Step 1: Feed data through encoder
        in_data = torch.cat([x[0], x[1]], dim=1)
        out.beta, out.post_logits, out.post_samples = self.encoder(in_data, is_training)
        post_samples = torch.cat(out.post_samples, 1)
        post_samples = torch.cat([post_samples, x[1]], dim=1)
        
        output_activations = self.decoder(post_samples)
        out.output_activations = self._energy_activation_fct(output_activations)
        return out
    
    def loss(self, input_data, fwd_out):
        logger.debug("loss")
        
        kl_loss, entropy, pos_energy, neg_energy = self.kl_divergence(fwd_out.post_logits, fwd_out.post_samples)
        ae_loss = self._output_loss(input_data, fwd_out.output_activations)
        ae_loss = torch.mean(torch.sum(ae_loss, dim=1), dim=0)
        
        return {"ae_loss":ae_loss, "kl_loss":kl_loss,
                "entropy":entropy, "pos_energy":pos_energy, "neg_energy":neg_energy}
    
    def generate_samples(self, num_samples=64, true_energy=None):
        """
        generate_samples()
        """
        true_energies = []
        num_iterations = max(num_samples//self.sampler.get_batch_size(), 1)
        samples = []
        for i in range(num_iterations):
            rbm_visible_samples, rbm_hidden_samples = self.sampler.block_gibbs_sampling()
            rbm_vis = rbm_visible_samples.detach()
            rbm_hid = rbm_hidden_samples.detach()
            
            if true_energy is None:
                true_e = torch.rand((rbm_vis.size(0), 1), device=rbm_vis.device).detach() * 100.
            else:
                true_e = torch.ones((rbm_vis.size(0), 1), device=rbm_vis.device).detach() * true_energy
            prior_samples = torch.cat([rbm_vis, rbm_hid, true_e], dim=1)
            
            output_activations = self.decoder(prior_samples)
            sample = self._energy_activation_fct(output_activations)
            
            true_energies.append(true_e) 
            samples.append(sample)
            
        return torch.cat(true_energies, dim=0), torch.cat(samples, dim=0)
    
    def _create_decoder(self):
        logger.debug("GumBoltCaloV7::_create_decoder")
        self._decoder_nodes[0] = (self._decoder_nodes[0][0]+1, self._decoder_nodes[0][1])
        return BasicDecoder(node_sequence=self._decoder_nodes, activation_fct=self._activation_fct,  cfg=self._config)
    
    def _create_encoder(self):
        """
        - Overrides _create_encoder in gumbolt.py
        
        Returns:
            Hierarchical Encoder instance
        """
        logger.debug("GumBoltCaloV6::_create_encoder")
        return HierarchicalEncoder(
            input_dimension=self._flat_input_size+1,
            n_latent_hierarchy_lvls=self.n_latent_hierarchy_lvls,
            n_latent_nodes=self.n_latent_nodes,
            n_encoder_layer_nodes=self.n_encoder_layer_nodes,
            n_encoder_layers=self.n_encoder_layers,
            skip_latent_layer=False,
            smoother="Gumbel",
            cfg=self._config)