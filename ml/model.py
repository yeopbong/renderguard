"""Paired visual observation model; inputs contain images and image geometry only."""
from __future__ import annotations
import torch
from torch import nn
from pathlib import Path
import hashlib
import urllib.request
import timm
from safetensors.torch import load_file

UPSTREAM_REVISION = "1824797e7887cbec1990e4adbd6675960a36c589"
UPSTREAM_SHA256 = "46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697"
UPSTREAM_URL = f"https://huggingface.co/timm/mobilenetv3_small_100.lamb_in1k/resolve/{UPSTREAM_REVISION}/model.safetensors"

def pretrained_file():
    path = Path(__file__).resolve().parents[1] / "data/pretrained/timm-mobilenetv3.safetensors"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        urllib.request.urlretrieve(UPSTREAM_URL, temporary)
        temporary.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Pretrained weight hash mismatch")
    return path

LABELS = ['clipping', 'overlap_or_occlusion', 'out_of_container', 'element_disappearance', 'layout_displacement']
INPUT_NAMES = ['local_before', 'local_after', 'context_before', 'context_after', 'geometry']

class ObservationModel(nn.Module):
    def __init__(self, context: bool = True, pretrained: bool = False):
        super().__init__()
        backbone = timm.create_model("mobilenetv3_small_100", pretrained=False)
        if pretrained:
            backbone.load_state_dict(load_file(str(pretrained_file())))
        self.encoder = nn.Sequential(backbone.conv_stem, backbone.bn1, *backbone.blocks.children())
        self.context = context
        width = 576 * 4 * (2 if context else 1) + 12
        self.head = nn.Sequential(nn.Linear(width, 128), nn.ReLU(), nn.Dropout(.15), nn.Linear(128, 5))

    @staticmethod
    def pair(a, b):
        return torch.cat((a, b, torch.abs(a - b), a * b), dim=1)

    def encode(self, x):
        return self.encoder(x).mean((2, 3))

    def features(self, local_before, local_after, context_before, context_after, geometry):
        # Separate calls preserve fixed branch boundaries for dynamic batch ONNX export.
        local = self.pair(self.encode(local_before), self.encode(local_after))
        if self.context:
            context = self.pair(self.encode(context_before), self.encode(context_after))
            return torch.cat((local, context, geometry), dim=1)
        return torch.cat((local, geometry), dim=1)

    def forward(self, local_before, local_after, context_before, context_after, geometry):
        return self.head(self.features(local_before, local_after, context_before, context_after, geometry))

    def set_stage(self, fine_tune: bool):
        for p in self.encoder.parameters():
            p.requires_grad_(False)
        if fine_tune:
            for layer in list(self.encoder.children())[-3:]:
                for p in layer.parameters():
                    p.requires_grad_(True)
        # BatchNorm statistics remain those of generic pretraining in all stages.
        self.encoder.eval()
        for m in self.modules():
            if isinstance(m, nn.modules.batchnorm._BatchNorm):
                m.eval()

    def train(self, mode=True):
        super().train(mode)
        self.encoder.eval()
        return self


def masked_bce(logits, targets, mask, positive_weight=None):
    loss = nn.functional.binary_cross_entropy_with_logits(logits, targets, reduction='none', pos_weight=positive_weight)
    return (loss * mask).sum() / mask.sum().clamp_min(1)
