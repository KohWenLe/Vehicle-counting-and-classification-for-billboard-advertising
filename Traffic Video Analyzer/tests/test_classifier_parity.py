"""Train/serve parity guards for the MobileNetV3 classifier.

The training notebook (MobileNetV3 training original.ipynb) feeds raw [0,255]
RGB via image_dataset_from_directory with NO preprocess_input call; the model
bakes a Rescaling(1/127.5, -1) layer into its graph. Serving therefore relies
on two facts these tests pin down:

1. keras' mobilenet_v3.preprocess_input is an identity function (it became a
   pass-through once preprocessing moved inside the model). If a TensorFlow
   upgrade ever changes that, every prediction silently degrades.
2. load_classifier_with_architecture assigns the archived weights correctly.
   Verified against the report's published validation accuracy (0.7143 on the
   seed-123 split) and locked here via a golden prediction on a synthetic
   image.

These tests skip cleanly when TensorFlow or the model file is unavailable, so
the suite still runs on machines without ML dependencies.
"""

import os
import unittest

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import tensorflow as tf
    from tensorflow.keras.applications.mobilenet_v3 import preprocess_input
except Exception:  # pragma: no cover - TF missing or broken install
    tf = None
    preprocess_input = None

try:
    # Pulls in cv2/ultralytics too; guard so partial ML installs skip cleanly.
    from backend.inference.pipeline import load_classifier_with_architecture
except Exception:  # pragma: no cover - cv2/ultralytics missing
    load_classifier_with_architecture = None

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "mobilenetv3_original.keras")

# Recorded from the shipped model (TF 2.19) on the synthetic gradient below.
GOLDEN_PROBS = [0.002664, 0.013653, 0.015535, 0.04074, 0.927408]


def _synthetic_image():
    h = np.linspace(0, 255, 224, dtype=np.float32)
    return np.stack(
        [
            np.tile(h, (224, 1)),
            np.tile(h[::-1], (224, 1)),
            np.full((224, 224), 128, np.float32),
        ],
        axis=-1,
    )


@unittest.skipIf(tf is None or np is None, "TensorFlow unavailable")
class PreprocessContractTests(unittest.TestCase):
    def test_mobilenet_v3_preprocess_input_is_identity(self):
        x = np.array([[0.0, 127.5, 255.0]], dtype=np.float32)
        y = np.asarray(preprocess_input(x.copy()))
        self.assertTrue(
            np.allclose(x, y),
            "mobilenet_v3.preprocess_input is no longer a pass-through; the "
            "serving pipeline now double-normalizes classifier inputs.",
        )


@unittest.skipIf(tf is None or np is None, "TensorFlow unavailable")
@unittest.skipIf(load_classifier_with_architecture is None, "pipeline deps (cv2/ultralytics) unavailable")
@unittest.skipUnless(os.path.exists(MODEL_PATH), "classifier weights not present")
class GoldenPredictionTests(unittest.TestCase):
    def test_loaded_model_reproduces_golden_prediction(self):
        model = load_classifier_with_architecture(MODEL_PATH)
        probs = np.asarray(model(_synthetic_image()[None, ...], training=False))[0]
        self.assertTrue(
            np.allclose(probs, GOLDEN_PROBS, atol=1e-3),
            f"Model output drifted from golden values: {probs.tolist()}",
        )


if __name__ == "__main__":
    unittest.main()
