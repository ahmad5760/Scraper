import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

import requests


def load_local_env(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_image_path(path_arg: str) -> Path:
    direct = Path(path_arg)
    if direct.exists():
        return direct

    prefixed = Path("load_dataset") / path_arg
    if prefixed.exists():
        return prefixed

    return direct


def encode_image_to_data_url(image_path: Path) -> str:
    extension = image_path.suffix.lower().lstrip(".")
    if extension == "jpg":
        extension = "jpeg"
    if extension not in {"jpeg", "png", "webp", "gif"}:
        extension = "jpeg"

    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{extension};base64,{encoded}"


def request_person_check(api_key: str, image_data_url: str, model: str) -> dict[str, str]:
    schema = {
        "name": "person_presence_check",
        "schema": {
            "type": "object",
            "properties": {
                "person_present": {
                    "type": "string",
                    "enum": ["yes", "no"],
                }
            },
            "required": ["person_present"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": schema,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "You detect whether at least one human person is visible in the image. "
                    "Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Is any person visible in this image? "
                            "Return JSON with person_present set to yes or no."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()

    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    result = str(parsed.get("person_present", "")).strip().lower()
    if result not in {"yes", "no"}:
        raise RuntimeError("Model response is missing a valid yes/no 'person_present' value.")
    return {"person_present": result}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check if a person is present in an image using GPT-4o Mini Vision."
    )
    parser.add_argument(
        "--image",
        default="dawah_t-shirt/1195_image.jpg",
        help="Image path. If relative path is not found directly, load_dataset/ prefix is tried.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI vision-capable model name.",
    )
    args = parser.parse_args()

    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY in environment.")

    image_path = resolve_image_path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image file not found: {image_path}")

    image_data_url = encode_image_to_data_url(image_path)
    result = request_person_check(api_key=api_key, image_data_url=image_data_url, model=args.model)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
