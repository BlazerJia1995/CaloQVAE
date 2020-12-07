# -*- coding: utf-8 -*-
"""
Autoencoder Base Class

Author: Eric Drechsler (dr.eric.drechsler@gmail.com)
"""
import torch
import torch.nn as nn

#logging module with handmade settings.
from DiVAE import logging
logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

# Base Class for Autoencoder models
class AutoEncoderBase(nn.Module):
    def __init__(self, input_dimension=None, activation_fct=None, config=None, **kwargs):
        super(AutoEncoderBase,self).__init__(**kwargs)
        #sanity checks
        if isinstance(input_dimension,list):
            assert len(input_dimension)>0, "Input dimension not defined, needed for model structure"
        else:
            assert input_dimension>0, "Input dimension not defined, needed for model structure"
        assert config is not None, "Config not defined"
        assert config.num_latent_units is not None and config.num_latent_units>0, "Latent dimension must be >0"
        
        # a short tag identifying the exact model, such as AE, VAE, diVAE...
        self._model_type=None
        # the main configuration namespace returned by configaro
        self._config=config
        # number of nodes in latent layer
        self._latent_dimensions=config.num_latent_units
        
        if len(input_dimension)>1:
            logger.warning("Received multiple input dimension numbers. Assuming multiple inputs.")
            self._input_dimension=input_dimension
        else:
            self._input_dimension=input_dimension[0]

        self._activation_fct=activation_fct
        self._dataset_mean=None

    def type(self):
        return self._model_type

    def _create_encoder(self):
        raise NotImplementedError

    def _create_decoder(self):
        raise NotImplementedError
    
    def __repr__(self):
        parameter_string="\n".join([str(par.shape) if isinstance(par,torch.Tensor) else str(par)  for par in self.__dict__.items()])
        return parameter_string
    
    def forward(self, x):
        raise NotImplementedError

    def print_model_info(self):
        for par in self.__dict__.items():
            if isinstance(par,torch.Tensor):
                logger.info(par.shape)
            else:
                logger.info(par)

    def set_dataset_mean(self,mean):
        self._dataset_mean=mean

if __name__=="__main__":
    logger.info("Running autoencoderbase.py directly") 
    logger.info("Success")