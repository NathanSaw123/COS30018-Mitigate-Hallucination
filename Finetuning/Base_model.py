import warnings
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
import torch

def main():
    warnings.filterwarnings('ignore') # Ignore warnings when display the output
    
    model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
    model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto", torch_dtype=torch.bfloat16)

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    streamer = TextStreamer(tokenizer) # type: ignore

    input_text = 'What does DNA stand for?'
    input_tokens = tokenizer(input_text, return_tensors="pt").to(model.device)

    output_tokens = model.generate(**input_tokens, streamer=streamer, max_new_tokens=100, do_sample=True, top_p=0.8)
    return output_tokens

if __name__ == "__main__":
    main()
