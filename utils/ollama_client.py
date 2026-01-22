"""
Ollama API client for vision and text models.
"""

import base64
import json
import requests
from pathlib import Path
from typing import Optional, List, Dict, Generator
import numpy as np
import cv2

from config import OLLAMA_BASE_URL, VISION_MODEL, TEXT_MODEL


class OllamaClient:
    """Client for interacting with Ollama API."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [m["name"] for m in models]
        except requests.RequestException as e:
            print(f"Error listing models: {e}")
            return []

    def has_model(self, model_name: str) -> bool:
        """Check if a specific model is available."""
        models = self.list_models()
        return any(model_name in m for m in models)

    def pull_model(self, model_name: str) -> bool:
        """Pull a model from Ollama registry."""
        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=600,
            )
            for line in response.iter_lines():
                if line:
                    status = json.loads(line)
                    if "status" in status:
                        print(f"  {status['status']}")
            return True
        except requests.RequestException as e:
            print(f"Error pulling model: {e}")
            return False

    def generate(
        self,
        model: str,
        prompt: str,
        images: Optional[List[str]] = None,
        stream: bool = False,
        **options,
    ) -> str:
        """
        Generate a response from the model.

        Args:
            model: Model name
            prompt: Text prompt
            images: List of base64-encoded images (for vision models)
            stream: Whether to stream the response
            **options: Additional options (temperature, top_p, etc.)

        Returns:
            Generated text response
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }

        if images:
            payload["images"] = images

        if options:
            payload["options"] = options

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()

            if stream:
                return self._handle_stream(response)
            else:
                return response.json().get("response", "")

        except requests.RequestException as e:
            print(f"Generation error: {e}")
            return ""

    def _handle_stream(self, response) -> Generator[str, None, None]:
        """Handle streaming response."""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]

    def generate_with_image(
        self,
        prompt: str,
        image: np.ndarray,
        model: str = VISION_MODEL,
    ) -> str:
        """
        Generate response from image input.

        Args:
            prompt: Text prompt
            image: OpenCV image (BGR format)
            model: Vision model name

        Returns:
            Generated response
        """
        image_b64 = self._encode_image(image)
        return self.generate(model, prompt, images=[image_b64])

    def generate_with_image_file(
        self,
        prompt: str,
        image_path: Path,
        model: str = VISION_MODEL,
    ) -> str:
        """
        Generate response from image file.
        """
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        return self.generate(model, prompt, images=[image_b64])

    def _encode_image(self, image: np.ndarray) -> str:
        """Encode OpenCV image to base64."""
        # Ensure BGR format for encoding
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        success, buffer = cv2.imencode(".png", image)
        if not success:
            raise ValueError("Failed to encode image")

        return base64.b64encode(buffer).decode("utf-8")

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> str:
        """
        Chat-style interaction with the model.

        Args:
            model: Model name
            messages: List of {"role": "user/assistant", "content": "..."}
            images: Optional base64 images

        Returns:
            Assistant response
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        if images:
            # Add images to the last user message
            for msg in reversed(payload["messages"]):
                if msg["role"] == "user":
                    msg["images"] = images
                    break

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")

        except requests.RequestException as e:
            print(f"Chat error: {e}")
            return ""


def check_ollama_setup() -> Dict[str, bool]:
    """
    Check Ollama setup and required models.

    Returns:
        Dict with status of server and each required model
    """
    client = OllamaClient()
    status = {
        "server_running": client.is_available(),
        "vision_model": False,
        "text_model": False,
    }

    if status["server_running"]:
        status["vision_model"] = client.has_model(VISION_MODEL)
        status["text_model"] = client.has_model(TEXT_MODEL)

    return status


def ensure_models_available() -> bool:
    """
    Ensure required models are available, pulling if necessary.

    Returns:
        True if all models are available
    """
    client = OllamaClient()

    if not client.is_available():
        print("ERROR: Ollama server is not running!")
        print("Please start Ollama with: ollama serve")
        return False

    required_models = [VISION_MODEL, TEXT_MODEL]

    for model in required_models:
        if not client.has_model(model):
            print(f"Pulling model: {model}")
            if not client.pull_model(model):
                print(f"Failed to pull model: {model}")
                return False

    print("All required models are available")
    return True


if __name__ == "__main__":
    # Check setup
    print("Checking Ollama setup...")
    status = check_ollama_setup()

    for key, value in status.items():
        icon = "OK" if value else "MISSING"
        print(f"  {key}: {icon}")

    if not all(status.values()):
        print("\nAttempting to fix missing components...")
        ensure_models_available()
