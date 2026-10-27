---
title: "On-Device Large Language Models on Android"
excerpt: "Why running LLMs on phones is worth the trouble, and two working Android demos — a RAG document-querying app built on Phi-3-mini and ONNX Runtime, and a multi-LoRA adapter-switching app on Gemma 2B."
date: "2024-12-14"
tags:
  - on-device ai
  - edge llm
  - onnx runtime
  - quantization
  - android
  - rag
---

_Written in December 2024. The small-model landscape has moved fast since — Phi-3-mini and Gemma 2 were the strong open options at the time of writing, and the benchmark numbers and library recommendations below reflect that moment rather than the current state of the art._

In recent years, businesses and professionals recognized the impressive capabilities of Large Language Models (LLMs) for generating text and completing various language-related tasks. However, LLM implementation comes with substantial challenges, primarily due to the extensive utilization of computational resources and energy, resulting in high operational costs for users. Consequently, a surge of research and development efforts now focus on creating more efficient and economical LLM deployment methods. At the forefront of this optimization research is the challenge of enhancing throughput and reducing latency while maintaining high-quality performance, all while using only a fraction of the typical computing resources. These efforts aim to make LLMs more accessible and practical for a broader range of applications and users.

The two approaches in solving the problem of LLMs excessively utilizing computational and energy resources are: (1) engineering optimization of LLMs to utilize fewer resources, and (2) improve the performance of smaller LLMs closer to the levels of large LLMs. The second approach showed promising results enabling deployment of models on resource-constrained devices such as mobile phones. Deploying LLMs, including Multimodal LMs (MLMs), on smartphones and other edge devices is transitioning from concept to reality.

An important question to ask at this juncture is: "what are the benefits of running LLM models on smartphones and edge devices?". The four reasons to persuade practitioners and businesses to deploy LLMs on devices are listed below:

1. **Improved accessibility:** On-device LLM deployment contributes to accessibility and empowers users in remote and disconnected environments due to the following reasons: (1) reduces reliance on external infrastructure, (2) eliminates dependency on cloud services, (3) avoids LLM subscription costs, and (4) operates without internet connectivity.
2. **Enhanced privacy:** Eliminating the need for external processing contributes to curbing apprehensions around data security. By confining operations to the device, sensitive information remains safeguarded, especially critical in regulated industries like finance and healthcare.
3. **Upgraded performance:** Rapid advancements in optimization techniques are enabling faster and more responsive on-device LLMs minimizing latency compared to cloud-based alternatives as well as enhancing interactivity for a better user experience.
4. **Customizability:** On-device deployment allows model adaptation (fine-tuned models) in a more private and controlled manner. Custom needs can be addressed without compromising data integrity or exposing confidential data.

## Use Cases

Two use cases are illustrated. First, a mobile app for intelligent document analysis and querying by deploying LLMs on device. Second, a multi-LoRA application that allows users to switch between different AI capabilities for various tasks, all powered by a single base model on their smartphone.

The reasons for illustrating these use cases are: (1) demonstrate the idea of deploying multiple LLMs on device to solve business problems, (2) leverage capabilities on intelligent document processing (IDP) and solve IDP problems on-device, and (3) advocate to privacy-focused industries such as finance and healthcare to find value from these approaches.

The starting point was an existing suite of reusable solutions built for addressing end-to-end document processing challenges. Two key areas tackled by its components are:

1. Key information extraction
2. Knowledge base-sourced question answering pipeline

Both components demonstrate efficient handling of large workloads through LLMs and embedding models in the backend. Adapting these essential functionalities from a larger solution to work effectively on lower-end devices presents a unique challenge and potentially, a significant milestone.

Industry-leading smartphone manufacturers are increasingly integrating competent AI models into their devices, driving the emergence of on-device applications. However, the need for use-case specific customization continues to be overlooked. When user requirements deviate from core feature sets, general LLMs are not always capable of handling more specialized tasks.

To address this limitation, the second use case focuses on providing the capability of accessing fine-tuned models to consumers, enabling domain-oriented customization. Recognizing the diversity of user needs, the approach incorporates support for multiple variations of the same base LLM. This strategy allows for expanding the scope of applications while working within the constraints of limited on-device resources.

## Models

Selecting an appropriate model is crucial to meet performance and functional goals. Sources like the OpenLLM leaderboard on HuggingFace serve as a starting reference, allowing quick comparison of model sizes with respect to task-specific performance metrics. Models excel in different areas, such as coding, reasoning, or subject-specific tasks like mathematical problem-solving. Licensing information and developer community support are also important factors to consider, ensuring appropriate, compliant usage, and potential issue resolution.

Microsoft's Phi-3-mini and Google's Gemma/Gemma 2 are popular open-source models in the smaller LLM segment, demonstrating performance competitive with models double their parameter count.

Phi-3-Mini-4K-Instruct, the conversation-oriented version, with 3.8 billion parameters trained on 3.3 trillion tokens, contends with models up to 13 billion parameters. It demonstrates robust results in: language understanding, mathematical reasoning, code generation, long context handling, and logical reasoning. The model achieves a 70.9% score on the MMLU benchmark and excels in tasks such as the ARC Challenge and BoolQ, indicating strong reasoning and comprehension capabilities.

Google's Gemma and Gemma 2, built on the same technology as the proprietary Gemini models, span 2 to 27 billion parameters (Gemma 2 ships in 2, 9, and 27 billion sizes). The Gemma models incorporate built-in safety advancements as well, and the Gemma 2B model is of particular interest due to in-built optimization for fast inference across diverse hardware.

Gemini Nano, a proprietary model, presents an alternative in the on-device model segment, offering API access for on-device setup without internet connectivity. Gemini Nano also provides functionalities beyond standard text generation, including: image understanding, speech transcription and text summarization. However, some multimodality-related options are available only on a restricted set of devices. Limited API access for developers has constrained experimentation with Gemini Nano models in the current project.

## Libraries

A variety of open-source libraries now enable efficient deployment of popular models. Examples include llama.cpp, Ollama, and Qualcomm's package for optimized mobile model deployment. The choice of library depends on the specific use case and available resources.

### ONNX Runtime

ONNX Runtime for C++ inference, integrated into Android applications using JNI, offers a powerful approach for on-device AI deployment. Key advantages include: (1) high performance, (2) hardware-agnostic nature, (3) minimal dependencies, (4) support for a broad range of devices, (5) consistent performance across environments, and (6) seamless deployment of models trained in PyTorch and TensorFlow. With strong community and industry backing, ONNX Runtime provides a flexible and efficient solution for mobile AI needs.

The integration process is narrowed down into the following steps:

1. Setting up the appropriate project structure
2. Configuring build tools
3. Writing and integrating native C++ code
4. Ensuring seamless communication between Java/Kotlin and C++

With the foundation of ONNX Runtime in place, we applied several optimization techniques to ensure peak efficiency in real-world scenarios.

### Optimization Techniques

The successful deployment of on-device AI requires careful optimization to balance performance with resource constraints. Various optimization techniques, from model compression to inference acceleration, allow complex AI models to run effectively on resource-constrained hardware such as mobile devices. The following key optimization strategies are implemented to achieve this balance, backed by Microsoft's published results for Phi-3-mini:

- **Quantization Techniques**: 4-bit block quantization. Microsoft's ONNX Runtime team reports that its 4-bit block-quantized Phi-3-mini builds for mobile and web are more than 2.5 times smaller than the original PyTorch version while maintaining high accuracy ([Microsoft, "Enjoy the power of Phi-3 with ONNX Runtime on your device"](https://huggingface.co/blog/Emma-N/enjoy-the-power-of-phi-3-with-onnx-runtime)).
- **Runtime Libraries**: ONNX Runtime Mobile over llama.cpp. In the same Microsoft benchmarks on a Samsung Galaxy S21, ONNX Runtime Mobile beat llama.cpp with short prompts and few tokens to generate, and was comparable in other cases.

## Demo 1: A Portable Document Intelligence App

The first demo is a portable document intelligence app centered on advanced document querying capabilities. The application's solution pipeline leverages Retrieval Augmented Generation (RAG), a process that combines information retrieval from a knowledge base with AI-powered answer generation through Large Language Models (LLMs). The system architecture consists of the following components:

1. **OCR: Google's ML Kit**
   - OCR functionality helps in handling text embedded in images and non-parseable formats
   - Google's ML Kit provides comprehensive machine learning tools for mobile developers
   - The Text Recognition API enables easy-to-setup text extraction in Android applications
   - Supports image and PDF formats
2. **Embedding Model: Universal Sentence Encoder (USE)**
   - Generates encoded text representations for accurate content matching
   - Captures semantic meaning in vectorized numerical format which can directly be processed and used for retrieval
   - Highly efficient and directly compatible with TensorFlow Lite
3. **Vector Database: ObjectBox**
   - High-performance NoSQL database optimized for mobile and IoT devices
   - Enables quick and efficient on-device storage and retrieval of vector embeddings
4. **Language Model: Phi-3-mini-4k-instruct**
   - Highly efficient 3.8B parameter version of the model
   - Aforementioned optimizations applied for boosting on-device performance

Built with Kotlin, the application achieves an optimal balance between performance and maintainability. Extensive testing has confirmed successful operation across multiple Android devices, including the Samsung Galaxy S20FE, Samsung Galaxy S23 Ultra, and Redmi Note 12.

The app stands as a compelling proof of concept for implementing advanced AI capabilities on mobile devices. The successful deployment across diverse hardware configurations showcases the application's versatility and resource-efficient design. The local data processing architecture ensures complete privacy preservation, making the solution particularly valuable for industries with stringent security requirements.

## Demo 2: MediaPipe Multi-LoRA App

The MediaPipe Multi-LoRA demo application showcases advanced versatility within mobile device constraints. The architecture requires only one base model stored on the smartphone, yet enables diverse functionalities through multiple LoRA adaptations. This unified platform allows seamless switching between different LoRA-tuned models, eliminating the need for storing multiple complete models while maintaining full functionality.

**Dynamic LoRA Integration** enables at-runtime loading of domain-specific LoRA adapters, expanding capabilities across industrial applications without additional model training. The memory footprint of LoRA adapters remains minimal, typically less than 1% of the original model's parameter count. This efficient architecture supports multiple specialized tasks from a single base model, including entity extraction, commercialization, programming assistance, and customer support functions.

The **Modular Architecture for Scalability**, built on the MediaPipe library, maintains clear separation between the Gemma 2B base model and associated LoRA extensions. This structured design creates a plug-and-play system, enabling straightforward integration of new LoRA adapters while maintaining the core inference pipeline's integrity. The modular approach significantly simplifies system updates and reduces maintenance requirements.

The **User-Friendly Interface** enables intuitive domain or use-case switching, allowing users to browse available models, view details, and switch between adapters effortlessly.

The Multi-LoRA app offers pre-tuned models for testing and supports the addition of user-created fine-tuned models. An easy-to-use notebook provides capabilities for quick model tuning and conversion to appropriate formats.

This approach maximizes functionality by improving customization options without significant additional resource usage, addressing hardware constraints typical in on-device systems. By bridging general-purpose LLMs with specific user requirements, the app enhances the versatility and applicability of on-device AI solutions.

## Conclusion

The two demonstrations showcase the remarkable performance and versatility achievable with on-device LLMs. By repurposing existing LLM solutions for resource-constrained devices, these applications expand the possibilities for on-device intelligence. The improved usability, convenience, and privacy offered by this setup cater to an expanded audience, paving the way for broader adoption of on-device AI across various sectors.
