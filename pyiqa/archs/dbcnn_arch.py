import os

import torch
import torchvision
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from pyiqa.utils.registry import ARCH_REGISTRY


class SCNN(nn.Module):
    """Network branch for synthetic distortions. 
    Modified from https://github.com/zwx8981/DBCNN-PyTorch/blob/master/SCNN.py

    """
    def __init__(self):
        super(SCNN, self).__init__()

        self.num_class = 39
        self.features = nn.Sequential(
                                * self._make_layers(3, 48, 3, 1, 1),
                                * self._make_layers(48, 48, 3, 2, 1),
                                * self._make_layers(48, 64, 3, 1, 1),
                                * self._make_layers(64, 64, 3, 2, 1),
                                * self._make_layers(64, 64, 3, 1, 1),
                                * self._make_layers(64, 64, 3, 2, 1),
                                * self._make_layers(64, 128, 3, 1, 1),
                                * self._make_layers(128, 128, 3, 1, 1),
                                * self._make_layers(128, 128, 3, 2, 1),
                                )

        self.pooling = nn.AdaptiveAvgPool2d(1)

        self.projection = nn.Sequential(
                                * self._make_layers(128, 256, 1, 1, 0),
                                * self._make_layers(256, 256, 1, 1, 0),
                                )

        self.classifier = nn.Linear(256, self.num_class)

    def _make_layers(self, in_ch, out_ch, ksz, stride, pad):
        layers = [
                nn.Conv2d(in_ch, out_ch, ksz, stride, pad),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(True),
                ]
        return layers

    def forward(self, X):
        X = self.features(X)
        X = self.pooling(X)
        X = self.projection(X)
        X = X.view(X.shape[0], -1)          
        X = self.classifier(X)
        return X


@ARCH_REGISTRY.register()
class DBCNN(nn.Module):
    """Full DBCNN network. 
    Modified from https://github.com/zwx8981/DBCNN-PyTorch/blob/master/DBCNN.py
	
	"""
    def __init__(self, fc=True):
        super(DBCNN, self).__init__()

        # Convolution and pooling layers of VGG-16.
        self.features1 = torchvision.models.vgg16(pretrained=True).features
        self.features1 = nn.Sequential(*list(self.features1.children())
                                            [:-1])
        scnn = SCNN()
              
        self.features2 = scnn.features
        
        # Linear classifier.
        self.fc = torch.nn.Linear(512*128, 1)
        
        if fc:
            # Freeze all previous layers.
            for param in self.features1.parameters():
                param.requires_grad = False
            for param in self.features2.parameters():
                param.requires_grad = False
            # Initialize the fc layers.
            nn.init.kaiming_normal_(self.fc.weight.data)
            if self.fc.bias is not None:
                nn.init.constant_(self.fc.bias.data, val=0)

    def forward(self, X):
        """Forward pass of the network.
        """
        X1 = self.features1(X)
        X2 = self.features2(X)
        
        N, _, H, W = X1.shape
        assert X1.shape == X2.shape, 'Feature shape of two branches should be the same'

        X1 = X1.view(N, 512, H*W)
        X2 = X2.view(N, 128, H*W)  
        X = torch.bmm(X1, torch.transpose(X2, 1, 2)) / (H*W)  # Bilinear
        X = X.view(N, 512*128)
        X = torch.sqrt(X + 1e-8)
        X = torch.nn.functional.normalize(X)
        X = self.fc(X)
        return X


