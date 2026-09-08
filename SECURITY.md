# Security

RenderGuard serves a private local review workspace on 127.0.0.1. Keep the port local. The API rejects foreign Host and Origin values and requires a per-process session token for mutations. Project screenshots may contain sensitive content; do not commit your workspace or export reports publicly without inspecting them.

Capture targets must be explicitly supplied development URLs on loopback. Redirects, subrequests, sockets and service access are restricted by the capture policy. Browser contexts are temporary and never reuse a personal profile. Capture is not a browser security boundary for hostile applications: run only development code you trust.

PNG imports are bounded by dimensions, encoded size and pixel count. Original images are retained, and reports embed escaped evidence without remote dependencies. Importing executable archives and arbitrary model serialization is unsupported. Published models use ONNX and pure safetensors; hashes are checked before inference. The browser demo has no image-upload endpoint or analytics.

Report a suspected issue through the repository's private vulnerability reporting facility when enabled. Do not attach private screenshots or secrets to a public issue.
