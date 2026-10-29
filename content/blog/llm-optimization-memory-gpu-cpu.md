---
title: "Fitting Really Big Models into Not-So-Big GPUs: Precision and Quantization"
excerpt: "How much GPU memory a model actually needs and how to cut it down — fp32, fp16 and bf16, what quantization trades away, LLM.int8() and bitsandbytes in practice, and the KV cache that grows on top of the weights."
date: "2024-12-14"
tags:
  - llm optimization
  - quantization
  - precision
  - kv cache
  - vram
  - inference
---

_Researched in 2024, and it shows. It predates FP8 and FP4 hardware support and the current generation of quantization methods (AWQ, GPTQ variants, MXFP4). The fundamentals below — why precision matters, how quantization trades accuracy for memory, where the KV cache's memory comes from — still hold. The specific library recommendations and benchmark numbers do not. Read it as a snapshot._

## Introduction

With bigger, state of the art achieving models being put out at an ever increasingly rapid pace nowadays, it is getting harder for practitioners to work on the cutting edge and spend hands-on time. Besides CPU processing being a bottleneck, and massive GPU access costs, another obstacle that comes in the way of experimenting with larger models is being able to store these models in the available memory at all. Traditionally, model weights have been stored as floats in the 32-bit format, also referred to as single precision. This format is known to be able to learn and manage the most amount of information possible. But despite the format's competence at storing significant amounts of information, the very same advantage presents a challenge as well. Massive information storage is a computational issue and makes it difficult to work with in machines which cannot store such blocks of information at a time.

This piece walks through what that storage actually costs, what lower-precision formats and quantization buy back, what they cost in quality and speed, and the second memory bill — the KV cache — that arrives once the model is serving requests.

## Precision Formats

Just to demonstrate the sizes that are being dealt with here, model size in bytes can be calculated as the number of parameters, multiplied by the precision size of choice in bytes:

```
Model size (bytes) = No. of Params * Precision Size (bytes)
```

Llama 2 7B is a useful reference point here, both because it is the smallest model in a lineup most practitioners have actually run, and because it is the model benchmarked later in this piece. Running that calculation across the precisions we care about:

| Precision | Bytes/param | Weights alone |
|---|---|---|
| fp32 (single) | 4 | ~28 GB |
| fp16 / bf16 (half) | 2 | ~14 GB |
| int8 | 1 | ~7 GB |
| int4 | 0.5 | ~3.5 GB |

The fp32 row is the problem in miniature. 28 GB of weights puts the *smallest* Llama 2 model beyond a 24 GB consumer card before a single token of context is allocated — and the KV cache discussed later adds to that. Halving the precision halves the bill, which is why the practical default settled on 16-bit long before quantization entered the picture.

The prospect of fitting larger models with limited compute made researchers in the area start asking the question — how much information out of what we initially store do we really need to have a model work at its full potential? Is there some part that we can do without, and in the process end up saving ourselves compute resources to direct elsewhere? Further academic explorations began to shed some light on this very hypothesis. Lower precision formats were tried out and found to demonstrate very reasonable performance applied across a variety of model types.

16-bit float representations have been extensively experimented with over time to try and find the option that could handle the widest applicable range of values expected in regular computation. Also called half-precision due to its nature of storing information with half the available number of bits, the recent standardized versions of the format have showed decent capability for learning tasks besides the reduced storage requirement.

<aside class="pull-quote" aria-hidden="true">
<p>How much information out of what we initially store do we really need to have a model work at its full potential?</p>
</aside>

In the conventional full precision, 1 bit refers to the sign of the float value, 8 are reserved for the exponent part, while the remaining 23 represent the mantissa, or the significand values of the floating point. This allows for the 32-bit format to represent the range -1e⁻³⁸ to 3e³⁸.

Half-precision, on the other hand, does away with 16 of the bits from the previous case and only has half of the storage memory to work with to accommodate the available bits differently. Here, 5 bits are assigned to the exponent representation, and 10 are for the mantissa, according to the latest IEEE 754 standard. The same 1 bit is used to represent the sign, which is maintained across all signed numeric representation formats. While the representable range with this 16-bit floating point format falls down to -6e⁻⁸ to 65504, this was found to be sufficient for several modeling tasks.

Seeing the potential in alternate precision formats, however, new formats began to be devised to tackle drawbacks in the existing ones. One such example is the popular bfloat16, or the Brain floating point format developed by Google Brain. While maintaining the same 16 bits as the memory space for byte representation, bfloat16 distributes its stock differently from how half precision does it. Here, 8 bits are assigned to the exponent, the same as what is found in the 32-bit representation. A reduced 7 bits are now used for the decimal point representation. This allows it to represent a wider range of numbers, i.e., from -1e⁻³⁸ to 3e³⁸, the same as what the 8 bits of exponent reservation in the single precision offers. The drawback is the precision up to which we can maintain for the floating point representation, which is less precise in this case. The big advantage of the greater range of representation is also that it prevents underflow and overflow.

<figure class="post-figure">
<svg viewBox="0 0 760 250" role="img" aria-label="Bit layout comparison of FP32, FP16 and BF16. FP32 uses 1 sign bit, 8 exponent bits and 23 mantissa bits. FP16 uses 1 sign, 5 exponent and 10 mantissa bits. BF16 uses 1 sign, 8 exponent and 7 mantissa bits, matching FP32's exponent width in half the total space.">
  <rect width="760" height="250" fill="#0a0a0a"/>
  <g font-family="ui-monospace, monospace" font-size="11">
    <text x="20" y="26" fill="#8a8a8a" letter-spacing="1.6">BIT ALLOCATION — 1 SIGN / EXPONENT / MANTISSA</text>
    <text x="20" y="72" fill="#f5f5f5" font-size="12">FP32</text>
    <rect x="88" y="58" width="18" height="30" fill="#2e2e2e" stroke="#1a1a1a"/>
    <rect x="106" y="58" width="150" height="30" fill="#ff2a2a" opacity="0.85"/>
    <rect x="256" y="58" width="431" height="30" fill="#242424" stroke="#1a1a1a"/>
    <text x="112" y="78" fill="#0a0a0a" font-size="10" font-weight="700">8 exp</text>
    <text x="262" y="78" fill="#8a8a8a" font-size="10">23 mantissa</text>
    <text x="700" y="78" fill="#8a8a8a" font-size="10">32 bits</text>
    <text x="20" y="132" fill="#f5f5f5" font-size="12">FP16</text>
    <rect x="88" y="118" width="18" height="30" fill="#2e2e2e" stroke="#1a1a1a"/>
    <rect x="106" y="118" width="94" height="30" fill="#ff2a2a" opacity="0.45"/>
    <rect x="200" y="118" width="188" height="30" fill="#242424" stroke="#1a1a1a"/>
    <text x="112" y="138" fill="#f5f5f5" font-size="10" font-weight="700">5 exp</text>
    <text x="206" y="138" fill="#8a8a8a" font-size="10">10 mantissa</text>
    <text x="700" y="138" fill="#8a8a8a" font-size="10">16 bits</text>
    <text x="20" y="192" fill="#f5f5f5" font-size="12">BF16</text>
    <rect x="88" y="178" width="18" height="30" fill="#2e2e2e" stroke="#1a1a1a"/>
    <rect x="106" y="178" width="150" height="30" fill="#ff2a2a" opacity="0.85"/>
    <rect x="256" y="178" width="132" height="30" fill="#242424" stroke="#1a1a1a"/>
    <text x="112" y="198" fill="#0a0a0a" font-size="10" font-weight="700">8 exp</text>
    <text x="262" y="198" fill="#8a8a8a" font-size="10">7 mant</text>
    <text x="700" y="198" fill="#8a8a8a" font-size="10">16 bits</text>
    <line x1="256" y1="52" x2="256" y2="214" stroke="#ff2a2a" stroke-width="1" stroke-dasharray="3 3" opacity="0.5"/>
    <text x="20" y="236" fill="#8a8a8a" font-size="10">BF16 keeps FP32's exponent width — same dynamic range, half the bits, paid for in mantissa precision.</text>
  </g>
</svg>
<figcaption>Where the bits go. FP16 splits its budget evenly-ish; BF16 spends it almost entirely on range.</figcaption>
</figure>

- **Underflow**: Not representing very small numbers falling under the minimum of a format's representation range.
- **Overflow**: Not representing very large numbers beyond the max of a format's representation range.

These 2 phenomena lead to significant instability in the training process. Rather than the required numerical/floating point values, NaN values replace them, thus affecting further computation by later layers of a network.

Other examples include Nvidia's TensorFloat 19-bit representation, AMD's fp24, and Pixar's PXR24 formats.

## Understanding Quantization

_The treatment of zero-point quantization and LLM.int8() in this section and the next draws heavily on Hugging Face's "A Gentle Introduction to 8-bit Matrix Multiplication" by Younes Belkada and Tim Dettmers [2], which remains the clearest explanation of the mixed-precision decomposition scheme. The framing of the scaling example below follows theirs._

For going even further with potential memory saving, lower-bit representations than 16-bit cannot be used directly, as these would not be able to store the required amount of information needed to achieve sufficient performance. **Quantization** is one such technique proposed to deal with this roadblock. Rather than dropping more bits, this method relies on rounding digits from float to int representations, paired with some strategy to manage precision loss.

In order to better familiarize ourselves with quantization, consider the following example. Assuming there exists data in a given range, say [-1.0, 1.0]. There may be several float values which can exist in this interval. One way of converting this range to a representation with a smaller scope would be to convert it to a fixed integer scale like [-127, 127]. For any conversion between these two scales, we would multiply a float value from the first interval by 127, which we can now call our scaling factor. This number is derived from the fact that multiplication of the max of the first range by this factor gives us the max of the new scale, while this also holds true for minimum to minimum conversion between these ranges.

Now, if we take a floating point number, 0.4, and wish to convert it to the [-127, 127] range and back, it would be done as follows:

1. `0.4 * 127 = 50.8 -> 51` (i.e., 50.8 is rounded up to 51 to fit with the new integer representation range)
2. `51 / 127 = 0.4015 ≈ 0.4` to get the original value again (i.e., the scaling factor is now divided rather than multiplied to reverse the scale conversion operation)

What can also be noticed here is the small errors which arise from rounding — an epsilon of 0.2 to get from 50.8 to 51, and a 0.0015 difference from the original value of 0.4 on the way back. These might seem minuscule at this moment, but these tiny values add up, with the errors propagating over the layers of a network, thus degrading model performance.

Another factor to keep in mind is that not all ranges are created the same. With vectors with varying ranges, an approach based around grabbing the absolute maximum from the series and calculating the scaling or quantization factor from it is preferred. This allows for conversion to Int8 ranges and back to floating point where the original range might not be so straightforward as the one mentioned in the previous example. This might be reminiscent of min-max scaling in some ways, with one of the main differences here being that it is ensured that there is always an integer value for representing 0 in the quantized domain when quantized, while this may not be the case when scaling.

Quantization can be broadly categorized into two primary types based on the stage of the pipeline at which it is performed:

1. **Quantization-Aware Training (QAT)** incorporates weight quantization at training time itself. This leads to improved model performance, but at the same time can be more computationally demanding. Methods like QLoRA work in this manner, accommodating the nuances of quantization.
2. **Post-Training Quantization (PTQ)** on the other hand performs the quantization on the weights of a model which has already been trained. This is an easier to implement solution which gives us some more flexibility to work with models that we might not have the compute to otherwise support with QAT methods, while allowing for additional memory requirement reductions. (This piece primarily covers PTQ methods.)

## Improved Quantization Techniques

A few further improvements have been proposed and put into practice, which are more common methods of carrying out the same concept of quantization but in more efficient ways which aid in preventing excessive performance degradation.

Rather than choosing a scaling factor for each tensor independently, the **vector-wise quantization** technique suggests performing this along an entire row or column instead. This makes it much faster than individually computing scaling factors while processing each tensor separately.

This is also made use of in the **LLM.int8()** method for performing int8 quantization. Besides vectorizing the quantization computation to improve efficiency, this alternative matrix multiplication method entails performance improvements over regular int8 quantization based on the concept that outlier features are primarily the ones responsible for quality degradation in the usual quantization flow. The reason for this is that while scaling down from a higher precision, the choice of the scaling factor gets too strongly influenced by vectors where there exist some extreme outlier values.

LLM.int8() promises zero degradation in performance by tackling the effect of outlier features via mixed precision computation. Put simply, this means identifying values which would gain advantage from being continued to be computed at a higher precision, while the remaining significant majority is multiplied in a lower 8-bit precision. The quantized portion can later be dequantized and added to the outliers which have been computed in their original 32/16-bit float values. This also has the additional advantage of only minimal slowdowns compared to complete float16 precision inference mode.

## Implementing Quantization

Models downloaded from the HuggingFace Hub are widely used for the convenience due to model usage and pipeline uniformity, along with the several other features for model sharing, downloading, uploading, etc., which the Hub makes available in an open-source fashion. Another significant advantage of this now is the ease of setting up quantization quickly while fine-tuning or for inference. HuggingFace has been powered by their link-up with the bitsandbytes library, along with the availability of several useful features from Accelerate, Optimum, and other similar services from HuggingFace themselves.

bitsandbytes provides a wide array of features allowing for incorporating state of the art quantization methods for quick and easy optimization. These help with saving memory while inferencing without drastic drop-offs in performance, and while maintaining throughput as well. LLM.int8() and NF4 quantization are features which exist out of the box with this library — in some cases only requiring a simple flag to be enabled for their usage (`load_in_8bit=True` is all that is needed to enable LLM.int8() quantization mode while loading a supported model from HuggingFace).

Accelerate also has another important feature which splits up any given model weights between the CPU and GPU memory, in case the GPU by default is not able to hold the entire model. Setting the `device_map` parameter to `'auto'` while loading any model from pretrained is all it takes to enable Accelerate to look out for cases where this sort of splitting needs to kick in.

## Results and Inferences

The objective here was to compare models before and after different types of quantization methods had been applied to them, and how this impacts pertinent performance-related factors — primarily, the output performance quality (based on some chosen metric), the size of the model we are actually able to load in and use, any drops or differences in speed observed at inference time, and any other factors that arise during testing.

**Memory Savings:** As expected, as per the previously described calculations for computing model size in memory, the benchmarks for model sizes that were able to be loaded in gives us a clearer picture of a more realistic setting with commonly used models. Comparing model size with GPU memory of the selected device, and then measuring how far different quantization techniques can take us in being able to move up a level and possibly run LLM tasks with a model with a "slightly" larger number of parameters, can provide a necessary perspective into the capabilities of a specified hardware setup.

Considering load time and run time memory usages while accommodating for some potential delta at run time, we can see the drop off in memory requirements for the same model, such as the Llama2-7b initially requiring almost 21 GiB unquantized, something which the more commonly available T4 GPU from NVIDIA would not even be able to load in with its 16GB VRAM capacity. This very same model comes down to a mere ~5.8 GiB later in its 4-bit quantized state. Thus, given a task, with its respective dataset, and some compute power at hand, such a reference can help align what potential exists in terms of model selection.

<aside class="post-stat" aria-hidden="true">
<p class="post-stat-figure">21 GiB <span class="post-stat-to">→ ~5.8 GiB</span></p>
<p class="post-stat-label">Llama2&#8209;7b on GPU · unquantized to 4&#8209;bit</p>
</aside>

**Performance Quality:** The next essential factor to consider — will these efficiently loaded models be able to perform at the same quality as their original unquantized versions? While newer methods currently in standardized use for quantization purposes promise to be fairly optimized in terms of retaining a maximum percentage of their original learnt capacity, some performance drop-offs are still to be expected. In cases where quality is key, these may be the deciding factor of the model-quantization method combination chosen, as quantized versions of models might fail in precision tasks which they were able to do well in in their original state.

Considering how the MPT model does in terms of pure performance on a structured and specific finetuned task, and how it fails to achieve a similar level of capability in its quantized state, it points towards the insight that such a model which takes up less compute to work might be beneficial in tasks which lie at the intersection of being restricted in terms of computational power but also not demanding pinpoint levels of accuracy.

**Model Throughput:** With quantization techniques being applied, there can also be observed a slowdown in operating performance of these models with the additional computation occurring at intermediate stages to make operation at a lower precision possible. This can be seen in the drop-offs in tokens/second generation of the same model across quantization methods — from taking an average of 30 seconds per sample in the MMLU case to up to ~1.5 minutes. Inference speeds being an integral part of cost calculations and the quality of a real-time setup itself, both the output token length and quantization type must be considered for such cases. Batch inference cases are less affected by this and can prioritize output quality, but for real-time cases a mixture of price and performance needs to be zeroed in on.

There do exist measures which can be taken to curb this slowdown, for example, with libraries like ExLlama or its newer V2 edition. These speed slowdowns are not inevitable, and resigning ourselves to not being able to pick quantized models due to insufficient throughput for inference is not the only option. Maintaining a decent output generation speed is quintessential to many real-time applications, and with this in mind, many techniques have been devised for maintaining or even improving quantized model throughput.

**Model Compatibility:** In some cases, it helps to note model-specific recommendations which have been provided keeping in mind the original state of training for a particular model, and how it can be best utilized at a fine-tuning or inference stage with the correct specifications/settings. The Llama2 models, for instance, were originally trained using the bfloat16 precision, as specified by Meta. For inference, float16 is picked. However, training the model in float16 is not a recommended practice and is known to produce NaN values which will be an obstacle to successful training. This specification can be made at load time itself with HuggingFace, with the model weights being cast to the required dtype on load.

## Beyond the Weights: The KV Cache

Everything above is about the weights. Serving adds a second memory cost on top of them — the key-value (KV) cache.

Decoding is autoregressive: one token per step, and every step attends over all the tokens before it. Without a cache, generating the *n*-th token means recomputing key and value projections for all *n-1* prior tokens — work that was already done at the previous step and whose result has not changed. Caching those projections in GPU memory turns that repeated quadratic work into an append: each step computes K and V for exactly one new token and concatenates them onto what is already stored. The cache is typically maintained per layer, since each layer attends over its own representations.

The trade is memory for compute, and it is worth being precise about how much memory, because this is where the ceiling on how many requests fit on one card comes from.

GPU memory during inference goes to two places: the weights, which are fixed, and the KV cache, which is not.

*Model weights* are the easy half — the calculation from earlier applies directly. Llama 2 7B at 16-bit precision is roughly 14 GB, and that figure does not move regardless of how many requests are in flight.

*The KV cache* is the half that scales, and it scales with traffic. Every token of every sequence in the batch needs its own K and V entries at every layer, so the cost per token is:

```
bytes_per_token = 2 * n_layers * d_model * bytes_per_element
```

The leading 2 is simply the K and V tensors. `d_model` is the model's hidden dimension, which for standard multi-head attention equals `n_heads * head_dim` — worth stating explicitly because it is easy to double-count these when reading a config file.

Multiply through by the tokens in flight and the batch width to get the total:

```
total_cache_bytes = batch_size * seq_len * bytes_per_token
```

Put Llama 2 7B's configuration through this — 32 layers, `d_model` of 4096, fp16 — and a single sequence at its full 4096-token context needs about 2 GB of cache on top of the 14 GB of weights. That ratio is the thing to internalise. At a batch size of 8 the cache is no longer a rounding error against the weights; it is comparable to them.

<figure class="post-figure">
<svg viewBox="0 0 760 268" role="img" aria-label="Stacked bar chart of Llama 2 7B GPU memory at 4096-token context. Model weights stay fixed at 14 gigabytes while the KV cache grows 2 gigabytes per sequence: 16 GB total at batch 1, 18 GB at batch 2, 22 GB at batch 4, and 30 GB at batch 8, which exceeds a 24 gigabyte card.">
  <rect width="760" height="268" fill="#0a0a0a"/>
  <g font-family="ui-monospace, monospace" font-size="11">
    <text x="20" y="24" fill="#8a8a8a" letter-spacing="1.6">LLAMA 2 7B @ FP16, 4096-TOKEN CONTEXT</text>
    <rect x="20" y="36" width="10" height="10" fill="#242424" stroke="#1a1a1a"/>
    <text x="36" y="45" fill="#8a8a8a" font-size="10">weights (fixed)</text>
    <rect x="146" y="36" width="10" height="10" fill="#ff2a2a" opacity="0.85"/>
    <text x="162" y="45" fill="#8a8a8a" font-size="10">KV cache (scales)</text>
    <line x1="544" y1="60" x2="544" y2="232" stroke="#ff2a2a" stroke-width="1" stroke-dasharray="4 3" opacity="0.65"/>
    <text x="550" y="72" fill="#ff2a2a" font-size="10">24 GB card</text>
    <text x="20" y="98" fill="#f5f5f5">batch 1</text>
    <rect x="88" y="82" width="266" height="24" fill="#242424" stroke="#1a1a1a"/>
    <rect x="354" y="82" width="38" height="24" fill="#ff2a2a" opacity="0.85"/>
    <text x="690" y="99" fill="#8a8a8a" font-size="10">16 GB</text>
    <text x="20" y="138" fill="#f5f5f5">batch 2</text>
    <rect x="88" y="122" width="266" height="24" fill="#242424" stroke="#1a1a1a"/>
    <rect x="354" y="122" width="76" height="24" fill="#ff2a2a" opacity="0.85"/>
    <text x="690" y="139" fill="#8a8a8a" font-size="10">18 GB</text>
    <text x="20" y="178" fill="#f5f5f5">batch 4</text>
    <rect x="88" y="162" width="266" height="24" fill="#242424" stroke="#1a1a1a"/>
    <rect x="354" y="162" width="152" height="24" fill="#ff2a2a" opacity="0.85"/>
    <text x="690" y="179" fill="#8a8a8a" font-size="10">22 GB</text>
    <text x="20" y="218" fill="#f5f5f5">batch 8</text>
    <rect x="88" y="202" width="266" height="24" fill="#242424" stroke="#1a1a1a"/>
    <rect x="354" y="202" width="304" height="24" fill="#ff2a2a" opacity="0.85"/>
    <text x="690" y="219" fill="#ff2a2a" font-size="10">30 GB</text>
    <text x="20" y="254" fill="#8a8a8a" font-size="10">Weights are a one-time cost. The cache is the one that decides how many users fit on the card.</text>
  </g>
</svg>
<figcaption>At batch 8 the cache alone (16 GB) exceeds the weights (14 GB), and the total overruns a 24 GB card.</figcaption>
</figure>

`batch_size` and `seq_len` are set by the workload rather than the model: longer contexts and more concurrent requests each grow the cache linearly. Once the weights fit, the cache sets the ceiling on concurrency, and it is why long contexts are expensive to serve. The `bytes_per_element` term is the same lever as before — a cache stored at lower precision shrinks in proportion, just as the weights do.

Batching requests and managing this cache well is a serving problem in its own right, and out of scope here; NVIDIA's "Mastering LLM Techniques: Inference Optimization" [7] is a good place to start.

## References

1. [bfloat16 floating-point format — Wikipedia](https://en.wikipedia.org/wiki/Bfloat16_floating-point_format)
2. Younes Belkada and Tim Dettmers, [A Gentle Introduction to 8-bit Matrix Multiplication for transformers at scale using Hugging Face Transformers, Accelerate and bitsandbytes](https://huggingface.co/blog/hf-bitsandbytes-integration) — Hugging Face
3. [Making LLMs even more accessible with bitsandbytes, 4-bit quantization and QLoRA](https://huggingface.co/blog/4bit-transformers-bitsandbytes) — Hugging Face
4. [Quantization — Hugging Face Transformers documentation](https://huggingface.co/docs/transformers/main/en/quantization)
5. Tim Dettmers et al., [LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale](https://arxiv.org/abs/2208.07339)
6. Tim Dettmers et al., [QLoRA: Efficient Finetuning of Quantized LLMs](https://arxiv.org/abs/2305.14314)
7. [Mastering LLM Techniques: Inference Optimization](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization/) — NVIDIA Developer Blog
8. [Half-precision floating-point format — Wikipedia](https://en.wikipedia.org/wiki/Half-precision_floating-point_format)
9. Hugo Touvron et al., [Llama 2: Open Foundation and Fine-Tuned Chat Models](https://arxiv.org/abs/2307.09288) — Meta
10. [turboderp/exllamav2: a fast inference library for running LLMs locally](https://github.com/turboderp/exllamav2)
