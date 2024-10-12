import logging

from transformers import AutoTokenizer, pipeline

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self):
        model_name = "meta-llama/Llama-3.2-3B-Instruct"
        # model_name = "meta-llama/Llama-3.2-1B-Instruct"
        # model_name = "meta-llama/Llama-3.1-8B-Instruct"
        # model_name = "ISTA-DASLab/Meta-Llama-3.1-70B-Instruct-AQLM-PV-2Bit-1x16"
        # model_name = "models--Qwen--Qwen2.5-14B-Instruct"
        self.pipeline = pipeline(
            "text-generation",
            model=model_name,
            device_map="auto",
            torch_dtype="auto",
            tokenizer=AutoTokenizer.from_pretrained(model_name),
        )

    def generate(self, prompt, system_instructions="You are an AI story teller."):
        messages = [
            {
                "role": "system",
                "content": system_instructions.strip(),
            },
            {"role": "user", "content": prompt.strip()},
        ]
        generated_text = self.pipeline(
            messages,
            max_new_tokens=128,
            pad_token_id=self.pipeline.tokenizer.eos_token_id,
        )[0]["generated_text"][-1]["content"]
        return generated_text
