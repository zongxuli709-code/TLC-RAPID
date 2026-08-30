# -*- coding: utf-8 -*-
"""Minimal export helpers kept for model type detection at runtime."""

import pandas as pd


def export_formats():
    """Return supported model suffixes used by DetectMultiBackend._model_type()."""
    x = [
        ["PyTorch", "-", ".pt", True, True],
        ["TorchScript", "torchscript", ".torchscript", True, True],
        ["ONNX", "onnx", ".onnx", True, True],
        ["OpenVINO", "openvino", "_openvino_model", True, False],
        ["TensorRT", "engine", ".engine", False, True],
        ["CoreML", "coreml", ".mlmodel", True, False],
        ["TensorFlow SavedModel", "saved_model", "_saved_model", True, True],
        ["TensorFlow GraphDef", "pb", ".pb", True, True],
        ["TensorFlow Lite", "tflite", ".tflite", True, False],
        ["TensorFlow Edge TPU", "edgetpu", "_edgetpu.tflite", False, False],
        ["TensorFlow.js", "tfjs", "_web_model", False, False],
        ["PaddlePaddle", "paddle", "_paddle_model", True, True],
    ]
    return pd.DataFrame(x, columns=["Format", "Argument", "Suffix", "CPU", "GPU"])
