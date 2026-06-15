"""Azure OpenAI image generation and editing (gpt-image-2).

Thin async wrapper around the Azure ``images.generate`` / ``images.edit``
endpoints. The async client is reused across calls; image bytes are passed
in memory (no disk writes), matching the bot's "no media storage" rule.
"""

import base64
import io
import logging

from openai import AsyncAzureOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# gpt-image models accept at most 16 reference images per edit request.
MAX_EDIT_IMAGES = 16

_client: AsyncAzureOpenAI | None = None


def _get_client() -> AsyncAzureOpenAI:
    """Lazily build (and cache) the Azure OpenAI async client."""
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY_IMAGE,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT_IMAGE,
        )
    return _client


def _named_buffer(data: bytes, index: int = 0) -> io.BytesIO:
    """Wrap raw bytes in a named buffer so the SDK can infer the mimetype."""
    buffer = io.BytesIO(data)
    buffer.name = f"image_{index}.png"
    return buffer


async def generate_image(prompt: str, size: str = "1024x1024") -> bytes:
    """Generate an image from a text prompt; return decoded PNG bytes."""
    client = _get_client()
    result = await client.images.generate(
        model=settings.AZURE_OPENAI_DEPLOYMENT_IMAGE,
        prompt=prompt,
        n=1,
        size=size,
    )
    return base64.b64decode(result.data[0].b64_json)


async def edit_image(
    images: list[bytes],
    prompt: str,
    mask: bytes | None = None,
) -> bytes:
    """Edit one or more reference images per the prompt; return PNG bytes.

    Pass a single image to restyle/modify it, or several (up to
    ``MAX_EDIT_IMAGES``) to combine them. An optional ``mask`` confines the
    edit to its transparent region (inpainting).
    """
    if not images:
        raise ValueError("edit_image requires at least one image")

    client = _get_client()
    buffers = [_named_buffer(data, i) for i, data in enumerate(images)]
    # The SDK accepts either a single file or a list; pass the bare buffer for
    # the common single-image case.
    image_arg = buffers if len(buffers) > 1 else buffers[0]

    kwargs: dict = {}
    if mask is not None:
        mask_buffer = io.BytesIO(mask)
        mask_buffer.name = "mask.png"
        kwargs["mask"] = mask_buffer

    result = await client.images.edit(
        model=settings.AZURE_OPENAI_DEPLOYMENT_IMAGE,
        image=image_arg,
        prompt=prompt,
        **kwargs,
    )
    return base64.b64decode(result.data[0].b64_json)
