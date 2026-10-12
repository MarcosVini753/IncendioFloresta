from __future__ import annotations

from xgboost.callback import TrainingCallback


class PreverNaCpu(TrainingCallback):
    def after_training(self, model):
        model.set_param({"device": "cpu"})
        return model
