# Third-party notices

RenderGuard application code is MIT licensed. Authored scene content and generated scene PNGs are dedicated under CC0-1.0. These licenses do not replace the licenses of dependencies or upstream model materials.

The generic MobileNetV3-Small initialization is the Apache-2.0 model from the pinned timm model card documented in [model documentation](docs/model.md). The paired network head, fine-tuning and exported weights modify that initialization. [The complete Apache license](artifacts/MODEL-LICENSE) accompanies the weights. ImageNet data are not included in this repository.

The browser distribution includes React, React DOM, Scheduler, fast-png, IOBuffer, pako and ONNX Runtime. Their unmodified license texts are retained in [web/public/licenses](web/public/licenses). ONNX Runtime's full upstream [license](web/public/licenses/onnxruntime.txt) and [third-party notices](web/public/licenses/onnxruntime-third-party.txt) are preserved. Runtime JavaScript and WebAssembly come from the same pinned 1.22.0 package. System fonts are used; the application does not redistribute a font file.

Development and local processing additionally use TypeScript, Vite, Playwright, pngjs, FastAPI, PyTorch, TorchVision, timm, NumPy, SciPy, scikit-learn, ONNX, safetensors, Pillow and other transitive packages pinned in the lockfiles. Their installed distributions retain their own license files. Installation does not transfer ownership of their code to this project.

Technical references include [Searching for MobileNetV3](https://arxiv.org/abs/1905.02244), [PyTorch Image Models](https://github.com/huggingface/pytorch-image-models), and [ONNX Runtime Web deployment documentation](https://onnxruntime.ai/docs/tutorials/web/deploy.html).
