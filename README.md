# Security Technical Debt Classification Prompt

This repository provides the prompt used in experiments for detecting and classifying Security Technical Debt (STD) in software issue comments using Large Language Models (LLMs).

## Prompt

The complete prompt used in the experiments is available in the following file:

`prompt`

The prompt was designed to classify issue comments into:

- **Security Technical Debt**
- **Not Security Technical Debt**

For comments classified as Security Technical Debt, the prompt also asks the model to identify the relevant **Common Weakness Enumeration (CWE)** when sufficient evidence is available.

## Models

The prompt was used with multiple Large Language Models, including:

- Claude
- GPT
- DeepSeek

## Reproducibility

The prompt is provided to document the instructions used in the experiments and to support reproducibility of the LLM-based classification process.
