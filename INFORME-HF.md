# Espacios de Hugging Face que editan una foto conservando la cara

### black-forest-labs/FLUX.1-Kontext-Dev
- puntos de entrada: /infer, /lambda
- probando «/infer» con ['input_image', 'prompt']
  ✓ **FUNCIONA** · guardada en HF-black-forest-labs__FLUX.1-Kontext-Dev.webp (59 KB)

### Qwen/Qwen-Image-Edit
- puntos de entrada: /infer
- probando «/infer» con ['image', 'prompt', 'rewrite_prompt']
  ✗ AppError: The requested GPU duration (240s) is larger than the maximum allowed

### multimodalart/Qwen-Image-Edit-Fast
- puntos de entrada: /infer
- probando «/infer» con ['image', 'prompt', 'rewrite_prompt']
  ✗ AppError: RuntimeError
