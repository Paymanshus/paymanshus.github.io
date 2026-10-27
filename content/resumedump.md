# Paymanshu Sharma

📞 +91 9810032357 | ✉️ [paymanshu@gmail.com](mailto:paymanshu@gmail.com) | 💼 [linkedin.com/in/paymanshus](https://www.linkedin.com/in/paymanshus/) | 🐙 [github.com/Paymanshus](https://github.com/Paymanshus) | 🌐 [paymanshus.github.io](https://paymanshus.github.io/) | 𝕏 [@paymanshu](https://x.com/paymanshu)

---

## Summary

Machine Learning Engineer at Maersk in Bangalore (April 2025 – present). The current work has two main tracks: production document AI for payments automation (Pay to Release and Payapps, scaling across 12+ countries, a few thousand documents a day) and Shipment CoCaptain, an agentic insights copilot over shipment and financial data. Before Maersk: a real-time Hinglish voice bot at Hike, and three years at Mphasis NEXT Labs (R&D) on document AI, LLM fine-tuning, multi-agent systems and applied research. Works across the whole path from a stakeholder's problem to production: discovery, build, evals, rollout and observability. Side projects lean towards voice and assistive tech, research tools and AI-assisted coding.

---

## Experience

### Maersk — *Machine Learning Engineer*
**April 2025 – Present | Bangalore, India**

Two main bodies of work: payments document AI in production, and Shipment CoCaptain for agentic insights. Also a patent filing, an executive KPI dashboard, and work on how the org builds with AI.

#### Payments automation — Pay to Release and Payapps (production document AI)

- Scaling payments automation across **12+ countries**: production document-AI pipelines (Pay to Release, Payapps) that read payment proofs and remittance emails with Azure Document Intelligence and LLMs, validate them against SAP, and auto-approve or post; **a few thousand documents/day** worth ~$1.3M/day.
- Made country onboarding **config-driven**: per-country prompt configs with isolated benchmarks and **regression evals** gating every launch, so new markets ship without degrading live ones. Iterative evals cut **human-in-the-loop** review toward ~80% straight-through (zero-touch) processing and ~21 FTEs of targeted manual-effort savings.
- Owned **ingestion reliability**: cut lost submissions from 30-60/day to under 5 with queue-first acceptance, hash-based idempotent dedup, root-caused upstream connection resets, and retry-by-default policies. Set **SLOs** for 99.9% no-loss ingestion and 30-minute processing via SLA-priority case ordering and Retry-After-aware backoff under SAP rate limits.
- Used SLO-driven **observability** (Prometheus, Grafana, Loki; drift alerts vs 7-day baselines, trace IDs) to catch and fix automation-rate dips, error spikes during volume surges, and silent failures; dashboards-as-code for support handover.

#### Shipment CoCaptain — agentic AI insights copilot

- Building Shipment CoCaptain for financial performance management: an **agentic AI insights** copilot over legacy shipment and financial data, turning natural language questions into grounded business analysis and surfacing insights beyond the ask. Cut manual analysis from **3-4 weeks per request to minutes**.
- Won sponsorship by pitching to area CFOs (North America, East Mediterranean), finance business partners and BI analysts; recurring **executive demos** with the CTIO. Selected as **1 of ~20 teams org-wide** to present at Copenhagen HQ.
- Architected a multi-stage **orchestrator-evaluator** pipeline with LangGraph: planning, structured outputs, parallel processing, recursive error handling, **LLM-as-a-judge** validation, and citation grounding.
- Custom **state management** with structured outputs instead of full conversation history, plus programmatic validation for sensitive cases.
- Shipped it end to end: a React frontend (asynchronous polling for long-running tasks, thinking indicators, citation tooltips, **LLM-generated Plotly charts**) over Azure PostgreSQL with composite-key indexing and row/column-level **RBAC**.

#### Patent — context management for agentic AI workflows

- **Patent filed**: *Method and System for Optimising Computational Resource Usage during Query Processing* (DKPTO, April 2026). It covers **context management** in agentic AI workflows: precise state architecting with injectable domain rules, definitions and formulae for grounding and safety, cutting **per agent/node context by up to 60%** (token count) versus full-state propagation.

#### Executive KPI dashboard

- Delivered an executive KPI dashboard with AI-generated dynamic widgets **in under 2 days**, challenging entrenched Power BI/Excel workflows. Built with **spec-driven development** (a design.md adapted from the company design system), Redis caching and a unified multi-source API.

#### AI-first org and forward-deployed teams

- Ran an internal workshop at Copenhagen HQ with engineering leadership on building an **AI-first org** and forward-deployed teams. Helped define the team's **hiring blueprint** for FDE and AI/ML roles, and advised teams on **right-sizing AI solutions** over default multi-agent complexity.

---

### Hike (Rush Gaming Universe) — *Machine Learning Engineer*
**December 2024 – April 2025 | Remote (Bangalore, India)**

- Built the AI outreach manager end to end: a **real-time multilingual voice bot** for colloquial Hindi-English (Hinglish) speakers in Tier-2 India, who are underserved by generic voice AI and text-based solutions. Designed for personal, high-trust engagement over cold ad-style outreach.
- Queue-based scheduler handling asynchronous call requests at scale via **SIP trunking**.
- Optimized the STT-LLM-TTS pipeline with filler responses and interim results to **reduce reply latency** by ~700ms (30%).
- Set up a configurable template for deploying customized bot agents with modifiable guardrails and speech guidelines, tested across varying configs, enabling **personalized user engagement** and offer targeting.

---

### Mphasis NEXT Labs (R&D Labs) — *Lead Data Scientist (Prev. Data Science Intern)*
**December 2021 – December 2024 | Bangalore, India**

- Translated client requirements into solution designs across enterprise **RFP/RFI** cycles, building proof-of-concepts on client data and pitching to mixed business and technical audiences.
- Spearheaded the structured **information extraction** solution in DeepInsights, a document intelligence suite for enterprise clients. Fine-tuned open-source LLMs with QLoRA on low-resource compute and optimized **inference throughput** with vLLM; outperformed Azure Document Intelligence and Textract on ~1K-document client datasets.
- **Implemented a novel** variant of DeBERTa's Disentangled Attention, incorporating document positional information, for a data extraction model trained from scratch. Engineered a task-specific **custom evaluation metric**.
- Designed a **multi-agent** conversational architecture with an LLM-powered **recommendation** system: a two-tower model, zero-shot retrieval, and long-context user and product insights, with **explainable** results.
- Led the creation and deployment of an intelligent document processing app for **mobile devices**, with extraction and RAG-based QA. **Optimized models** with ONNX runtime and quantization, with ObjectBox as the vector database.
- Directed a **scalable SaaS product** on AWS: CloudFormation, ECS/Fargate microservices, and GPU-enabled EC2 autoscaling driven by Lambda and SQS.
- Built a **multi-modal fusion transformer** for audio-video-text retrieval, using a combinatorial contrastive loss for cross-modal representation learning.
- Built a Flower-based **distributed federated learning** pipeline on edge devices with AWS Greengrass, for a medical image classification use case.
- Applied a modified multi-modal autoencoder for **structured data imputation** on an IoT sensor-based behaviour study dataset, boosting downstream classification accuracy by ~8%.
- Developed a chatbot for contact-centre agent assistance using **prompt engineering and chaining** with GPT-3.5, Whisper for STT and open-source TTS, also giving agents performance feedback.
- Deployed 5+ projects in anomaly detection, multi-modal learning and NLP via SageMaker, listed on the AWS Marketplace after **containerization**.
- Created a Streamlit dashboard for anomaly detection, analysis and monitoring, with LIME and SHAP-based **explainability**.
- Applied Guided LDA models to detect prominent aspects in Amazon product reviews, fine-tuned in a semi-supervised approach.

---

### MetFlux Research (IIT Bombay) — *Computer Vision and Signal Processing Research Intern*
**June 2021 – September 2021 | Remote (Mumbai, India)**

- Formulated algorithms to estimate HR, RR, SpO2 and other **physiological parameters** from smartphone face and fingertip videos, for a low-cost at-home health-check app, under Prof. K. V. Venkatesh.
- Improved **PPG signal quality** by testing signal processing, smoothing and dynamic peak detection algorithms (OpenCV, dlib, SciPy) on manually collected test data, for reproducible, device-agnostic results.
- Implemented an image processing and signal-quality validation pipeline, achieving a **55% improvement** in MAE after classical and ML experiments.

---

### Amicus.ai — *Founding Team Member and Data Scientist*
**February 2021 – June 2021 | Remote (Mumbai, India)**

- Built v1 of a **legaltech** product bringing NLP to legal case analysis: BERT **named entity recognition (NER)** models and regex rule-based extraction over scraped, unstructured, varied-format legal text from 100,000+ case files, covering over 70% of it.
- Built interactive data visualizations on a Dash/Plotly web dashboard.

---

### Open Health Systems Laboratory — *Web and Research Intern*
**August 2020 – January 2021 | Remote (International)**

- Carried out **preliminary research** and **data collection** for biomedical research proposals in Ayurveda and Oncology.
- **Coordinated** a cross-functional team building and managing OHSL-affiliated microsites with Drupal.

---

### Sapio Analytics — *Data Analyst Intern*
**April 2020 – June 2020 | Remote (Mumbai, India)**

- Built the front end of a state-wise COVID Response Dashboard with an interactive, granular map view.
- **Headed** a sub-team for GeoJSON and demographic data collection (scraping, then manual verification), and built Tableau **visualizations** of district data to help state governments with policy decisions.

---

### WorkAmp — *Frontend Developer and Analyst Intern*
**March 2020 – April 2020 | Remote (Mumbai, India)**

- Developed a **web app** MVP for resource management in office spaces, connected to MongoDB, and helped ideate it from an analysis of office needs.

---

### Awarathon — *AI Intern*
**July 2019 – December 2019 | Mumbai, India**

- Developed computer vision and speech assessment algorithms for an **interviewee video screening** platform used by college and corporate clients: speech cadence, tone and pitch analysis, gaze estimation, gesture recognition and multilingual transcription.
- Benchmarked AWS and GCP APIs and added the best method to the main pipeline. Tested on **200+ client clips** and incorporated into the primary codebase.

---

## Projects and Research Work

**Multilingual AAC Communication App** | *React Native, Expo, ElevenLabs, Cartesia*
Building an assistive communication (AAC) app with native Hindi-English code-switching, which existing AAC apps treat as separate modes. Personalized next-token phrase prediction, and a three-tier latency architecture for TTS (pre-rendered cache, on-demand cached, streaming) balancing instant response against synthesis cost.

**CereBro: Auditable Opinion Research Engine** | *Next.js, React, Supabase, Vercel*
Built a deep-research opinion mining engine across Reddit, HN, X and the web: the LLM extracts and clusters claims, while deterministic weighting with snippet-level source traceability enables instant zero-LLM-call re-scoring when sources are re-weighted.

**Agent Skills** | *Claude Code, Agent Skills spec, npx* | [github.com/Paymanshus/skills](https://github.com/Paymanshus/skills)
Published model-agnostic agent skills for AI-assisted coding built around cost-minimization: tiered task routing, one-time codebase specs over repeated exploration, and planning workflows that compile into parallel multi-session execution packages.

**AudioAnalytics: Emotion Detection Package** | *Python, TensorFlow, Librosa, PyPI*
Published an open-source PyPI package that extracts audio features and predicts emotion with a 1D CNN model.

**COVID Mythbuster Bot** | *Python, TensorFlow/Keras, Flask, nltk, Twilio*
Built a bot to detect fake news related to COVID-19, evaluated with F1 score on a manually collated dataset. Deployed on WhatsApp, Telegram and as a live web app.

**Paragon: Crime Detection Center** | *Python, TensorFlow/Keras, PyTorch, Streamlit, Pandas, NumPy*
A crime detection center prototype in Streamlit: face verification with Haar Cascades and Siamese Networks, action recognition from surveillance videos with CNN-LSTM, and statistical region-based crime prediction.

**iKitchen Aid** | *Python, Flutter, TensorFlow/Keras, TensorFlow Lite*
A Flutter app using YOLOv4 object detection to identify kitchen items, to help visually impaired people. Scraped, cleaned and tagged Google Images to build a training dataset of condiment images.

**Song Analysis and Recommendation System** | *Python, scikit-learn, Flask, Spotify API*
A content-based recommendation system built by evaluating similarity measures, with unsupervised clustering of song features and a method for user-specific playlist suggestions without listening history.

**Effect of Gaming on Students** | *R, Excel*
Ran a survey and hypothesis tests on the data to show trends between gaming and various aspects of a student's life.

**Gaze Estimation and Saliency Prediction Pipeline to Study Visual Attention for E-Commerce Websites** *(Undergraduate Thesis)*

---

## Honors and Awards

**LLM Prompt Recovery Challenge: Bronze Medal** | *Kaggle Competition*
Top 9% of 2200 participants as a solo entrant, on prompt jailbreaking and evaluation.

**Bajaj Finserv Hackathon: National-level Runners-Up** | *Search and Recommendation Engine*
2nd overall and 1st in category among 3000+ teams from 200+ colleges. Built a BERT-embedding recommendation engine on data mined from the Finserv website to improve their search.

**ACM Mumbai Hackathon: Region-level Winners** | *Ideation, prototyping and app development*
Developed Entrenet, a Flutter app connecting entrepreneurs, investors and job seekers.

**SIH Internal Hackathon: College-level Winners** | *ML app prototyping and pitching*
Presented an ML-enabled crop-detection app prototype for farmers; placed 1st at college level.

---

## Technical Skills

**Languages:** Python, SQL, C++, JavaScript/TypeScript, Dart (Flutter)

**AI/ML:** LLMs, Agentic Systems, LangGraph/LangChain, MCP, RAG & GraphRAG, LLM Evals & LLM-as-a-Judge, LangSmith/Langfuse, Context Engineering, Harness Engineering, Fine-tuning (LoRA/QLoRA), vLLM, ONNX, Quantization, PyTorch, Transformers, NLP, Document AI, Voice AI, Computer Vision, Signal Processing, Multimodal Learning, Recommendation Systems

**Engineering:** AWS, Azure, GCP, Docker, Microservices, CI/CD, FastAPI, PostgreSQL, Redis, Azure Service Bus, Prometheus, Grafana, Loki, React, Next.js, Git, Linux

**Also used:** R, HTML, CSS, Deep Learning, Web Scraping, ETL, APIs, Tableau, Excel, Figma

**Product and Delivery:** Stakeholder Discovery, Solution Scoping, PoC-to-Production, Executive Demos and Pitching, Spec-Driven Development, Rapid Prototyping

---

## Education

**MPSTME, Narsee Monjee Institute of Management Studies, Mumbai** | 2018 – 2022
Bachelor of Technology in Data Science — CGPA: 3.82/4.0 | Mumbai, India

**Delhi Public School, Gurgaon** | 2018
President, NODE (Computer Club) | Gurgaon (NCR), India. Managed a 50+ member club across grades and organized district-level inter-school events.

---

## Relevant Coursework

Data Structures & Algorithms • DBMS (SQL, MongoDB) • Statistics • Predictive Modelling • NLP • Computer Vision • Applied Mathematics

---

## Misc. Activities

**Rotaract Club of Bombay Airport** | *July 2019 – July 2021*
Initiated and led community projects, including the Open School program reaching 150+ underprivileged students, with national media coverage (The Times of India, 92.7 Big FM). Mentored teams in the Technology for Change program, including one building an Indian Sign Language translation app.

**Enactus** | *July 2019 – July 2020*
On-field research and business venture conceptualization for community upliftment through social entrepreneurship.
