"""
DVAE++ PyTorch

Author: Abhi (abhishek@myumanitoba.ca)
"""

# PyTorch imports
import torch

# Torchviz imports
from torchviz import make_dot

# DiVAE imports
from models.autoencoders.discreteVAE import DiVAE
from models.rbm.rbm import RBM
from models.samplers.pcd import PCD

from utils.dists.distributions import Bernoulli

from models.networks.hierarchicalEncoder import HierarchicalEncoder
from models.networks.basicCoders import BasicDecoder

from DiVAE import logging
logger = logging.getLogger(__name__)

class DiVAEPP(DiVAE):
    
    def __init__(self, **kwargs):
        super(DiVAEPP, self).__init__(**kwargs)
        self._model_type = "DiVAEPP"
        
    def _create_encoder(self):
        """
        - Overrides _create_encoder in discreteVAE.py
        
        Returns:
            Hierarchical Encoder instance
        """
        logger.debug("")
        return HierarchicalEncoder(
            input_dimension=self._flat_input_size,
            n_latent_hierarchy_lvls=self.n_latent_hierarchy_lvls,
            n_latent_nodes=self.n_latent_nodes,
            n_encoder_layer_nodes=self.n_encoder_layer_nodes,
            n_encoder_layers=self.n_encoder_layers,
            skip_latent_layer=False,
            smoother="MixtureExp",
            cfg=self._config)
    
    def _create_sampler(self):
        """
        - Overrides _create_sampler in discreteVAE.py
        
        Returns:
            PCD Sampler
        """
        return PCD(batchSize=128, RBM=self.prior, n_gibbs_sampling_steps=40)
    
    def forward(self, x):
        """
        - Overrides forward in discreteVAE.py
        
        Returns:
            out: output container 
        """
        logger.debug("forward")
        
        #see definition for explanation
        out=self._output_container.clear()
      	
	#TODO data prep - study if this does good things
        input_data_centered=x.view(-1, self._flat_input_size)-self._dataset_mean
        
	#Step 1: Feed data through encoder
        out.beta, out.post_logits, out.post_samples = self.encoder(input_data_centered)
        post_samples = torch.cat(out.post_samples, 1)
        
        output_activations = self.decoder(post_samples)
        out.output_activations = output_activations+self._train_bias
        out.output_distribution = Bernoulli(logits=out.output_activations)
        out.output_data = torch.sigmoid(out.output_distribution.logits)
        
        """
        Autograd graph visualization
        
        # Create the dot objects using torchviz
        post_logits_dot = make_dot(torch.cat(out.post_logits, 1), params=dict(self.encoder.named_parameters()))
        post_samples_dot = make_dot(post_samples, params=dict(self.encoder.named_parameters()))
        
        # Save the dot objects
        post_logits_dot.save(filename='post_logits.dot')
        post_samples_dot.save(filename='post_samples.dot')
        
        output_activations_dot = make_dot(output_activations)
        output_activations_dot.save(filename='output_activations.dot')
        """
        
        return out
    
    def loss(self, input_data, fwd_out):
	    logger.debug("loss")
    
	    kl_loss=self.kl_divergence(fwd_out.beta, fwd_out.post_logits, fwd_out.post_samples)

	    ae_loss_matrix=-fwd_out.output_distribution.log_prob_per_var(input_data.view(-1, self._flat_input_size))
	    ae_loss_per_sample = torch.sum(ae_loss_matrix,1)
	    ae_loss = torch.mean(ae_loss_per_sample)

	    loss = ae_loss + kl_loss
 
	    return {"loss":loss, "ae_loss":ae_loss, "kl_loss":kl_loss}
        
    def kl_divergence(self, beta, post_logits, post_samples, is_training=True):
        """
        - Compute KLD b.w. hierarchical posterior and RBM prior for DVAE++
        - See (https://github.com/QuadrantAI/dvae/blob/master/rbm.py#L139) for original 
          tf implementation
        - Overrides kl_divergence in discreteVAE.py
        Args:
            post_dists: List of dist objects
            post_samples: Approximate post samples (zeta)
        Returns:
            kl_loss: "Approximate integral KLD" loss whose gradient equals the
            gradient of the true KLD loss
        """
        logger.debug("kl_divergence")
        
        # Entropy component of the KLD loss
        entropy = 0
        logit_q = []
        log_ratio = []
        
        # Compute and sum the entropy for each hierarchy level
        for logits, samples in zip(post_logits, post_samples):
            factorial = self.encoder.smoothing_dist(logits=logits, beta=beta)
            entropy += torch.sum(factorial.entropy(), 1)
            log_ratio.append(factorial.log_ratio(samples))
            
        logit_q = torch.cat(post_logits, 1)
        log_ratio = torch.cat(log_ratio, 1)
        samples = torch.cat(post_samples, 1)
        
        num_latent_layers = len(post_logits)
        
        # Mean-field solution for num_latent_layers == 1
        if num_latent_layers == 1:
            log_ratio *= 0.
            
        if is_training:
            cross_entropy = self.cross_entropy_from_hierarchical(logit_q, log_ratio)
        else:
            cross_entropy = - self.log_prob(samples, is_training)
            
        # Add contribution of the logZ term to the cross entropy
        rbm_visible_samples, rbm_hidden_samples = self.sampler.block_gibbs_sampling()
        rbm_vis = rbm_visible_samples.detach()
        rbm_hid = rbm_hidden_samples.detach()
        
        batch_energy = (- torch.sum(torch.matmul(rbm_vis, torch.matmul(self.prior.get_weights(), rbm_hid.t())), 1) 
                        - torch.matmul(rbm_vis, self.prior.get_visible_bias())
                        - torch.matmul(rbm_hid, self.prior.get_hidden_bias()))
        neg_energy = - torch.mean(batch_energy, 0)
        cross_entropy = neg_energy + cross_entropy

        kl_loss = cross_entropy - torch.mean(entropy, 0)
        
        return kl_loss
    
    def cross_entropy_from_hierarchical(self, logits, log_ratio):
        """
        Compute the cross-entropy b/w a hierarchical distribution and
        an unnormalized Boltzmann machines
        -
        Args:
            logits: Bernoulli logits for all hierarchy levels (Concatenated)
            log_ratio: Log PDF ratio for the smoothing transformations
            
        Returns:
            cross_entropy
        """
        num_var_rbm = (self._config.model.n_latent_hierarchy_lvls*self._latent_dimensions)//2
        
        logit_q1 = logits[:, :num_var_rbm]
        logit_q2 = logits[:, num_var_rbm:]
        
        log_ratio_1 = log_ratio[:, :num_var_rbm]
        
        q1 = torch.sigmoid(logit_q1)       
        q2 = torch.sigmoid(logit_q2)
        q1_pert = torch.sigmoid(logit_q1 + log_ratio_1)
        
        cross_entropy = (- torch.matmul(q1, self.prior.get_visible_bias())
                         - torch.matmul(q2, self.prior.get_hidden_bias())
                         - torch.sum(torch.matmul(q1_pert, torch.matmul(self.prior.get_weights(), q2.t())), 1))
                         
        return torch.mean(cross_entropy, 0)
