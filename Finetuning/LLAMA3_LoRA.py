import warnings
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer, TrainingArguments 
from datasets import load_dataset 
from peft import get_peft_model, LoraConfig 
import torch 
from trl import SFTTrainer
import math
#test

# Show the number of trainable parameters
def print_trainable_parameters(model):
    trainable_params = 0
    all_params = 0
    
    for _, param in model.named_parameters():
        all_params += param.numel()
        if param.requires_grad:
            trainable_params += param.numel()
    print(f"Trainable parameters: {trainable_params} || all params: {all_params} || trainable %: {100 * trainable_params/all_params}" )
    
# Interface to interact with the model
def generate_output(model, tokenizer, question, alpaca_prompt):
    streamer = TextStreamer(tokenizer) # Type: ignore

    input_text = [
        {"role": "system", "content": alpaca_prompt},
        {"role": "user", "content": question},
    ]
    input_tokens = tokenizer.apply_chat_template(input_text, return_tensors="pt").to(model.device)
    
    with torch.cuda.amp.autocast(): # Make sure the model and input are in the same fp16 format
        output_tokens = model.generate(input_tokens, streamer=streamer, max_new_tokens=256, do_sample=True, top_p=0.8, pad_token_id=tokenizer.eos_token_id)
    return output_tokens

# Tokenize and formating
def tokenize_function(examples, alpaca_prompt, EOS_TOKEN):
    inputs = examples["Question"]
    outputs = examples["Answer"]

    texts = []
    
    for input, output in zip(inputs, outputs):
        text = alpaca_prompt + "\n" + "### Question: " +  input + "\n","### Answer: " +  output + EOS_TOKEN
        texts.append(text)
        
    return {"text": texts}

# Freezing the original weights
def freeze_model(model):
    for param in model.parameters():
        param.requires_grad = False # Freeze the model - train adapters later
        
        if param.ndim == 1:
            param.data = param.data.to(torch.float32) # Cast the small parameters (layernorm) to fp32 fpr stability
            
# Evaluate the model
def evaluate_model(trainer):
    eval_results = trainer.evaluate()
    return f"Perplexity: {math.exp(eval_results["eval_loss"]):.2f}"
            
def main():
    warnings.filterwarnings('ignore') # Ignore warnings when display the output
    
    # CONFIGURATION
    
    # LoRA config (adapter)
    config = LoraConfig(
        r = 1,
        lora_alpha=32,
        lora_dropout=0.05, #kind of like a regularization dropout
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    # Config arguments for the training process
    training_args = TrainingArguments(
            per_device_train_batch_size= 1, # Batch size per GPU (1 batch contain 1000 data points)
            per_device_eval_batch_size= 1, # Batch size for evaluation
            gradient_accumulation_steps = 4, # Accumulate gradients for larger batch size
            eval_accumulation_steps= 4, # Accumulate evaluation results for larger batch size
            warmup_steps = 5,
            logging_steps = 1,
            learning_rate = 1e-4, # Learning rate change
            fp16 = True, # Use mixed precision training for faster training
            optim = "adamw_8bit", # Use 8-bit optimization for faster training
            weight_decay = 0.01,
            lr_scheduler_type = "linear", # Control learning rate change
            seed = 3407,
            output_dir = "LLaMA-3-8B-Instruct-Fine-Tuned-LoRA/medical_2",
            group_by_length = True, # Group samples of same length to reduce padding and speed up training
            max_steps = 120,
        )
    
    # LOADDING
    
    # Load device
    def get_device_map() -> str:
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    
    device = get_device_map()

    # Load base model
    model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
    model = AutoModelForCausalLM.from_pretrained(model_id, device_map=device, torch_dtype=torch.bfloat16)
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    EOS_TOKEN = tokenizer.eos_token # End of sequence token
    tokenizer.pad_token = tokenizer.eos_token
    
    # Load the dataset
    data_file = "Finetuning/Dataset/medical_2/medDataset_processed.csv"
    
    dataset = load_dataset('csv', data_files=data_file, split='train')
    
    # Split the dataset into training and testing
    dataset = dataset.train_test_split()
    
    # IMPLEMENTING LORA TECHNIQUE
    
    # Freezing the original weights
    freeze_model(model)
    
    # Integrate the adapter with the base model
    model = get_peft_model(model, config)

    # Print the trainable parameters
    print_trainable_parameters(model)
    
    # DATA PREPROCESSING AND TOKENIZING
    
    # Create the prompt
    alpaca_prompt = "Below is  a question. Answer that question appropriately."
    
    # Tokenize the dataset
    
    tokenized_dataset = dataset.map(tokenize_function, fn_kwargs= {"alpaca_prompt": alpaca_prompt, "EOS_TOKEN": EOS_TOKEN} , batched=True)
    
    # TRAINING
    
    # Training setup
    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = tokenized_dataset['train'],
        eval_dataset= tokenized_dataset['test'],
        dataset_text_field = "text",
        max_seq_length = 512,
        packing = False, # Can make training 5x faster for short sequences.
        args = training_args,
    )
    
    # EVALUATING
    questions = ["What is the capital of France?"]
    
    # Evaluate the base model
    
    # print("Base model predictions:")
    # for question in questions:
    #     print(generate_output(model, tokenizer, question, alpaca_prompt))
    
    # print(evaluate_model(trainer)) # Evaluate using perplexity
    
    # Start training
    # trainer.train()
    
    # Evaluate the fine-tuned model
    
    print("Fine-tuned model predictions:")
    for question in questions:
        print(generate_output(model, tokenizer, question, alpaca_prompt))
        
    # print(evaluate_model(trainer)) # Evaluate using perplexity
        
    # Save the model
    # model.save_pretrained("LLAMA3_Fine-tuned")

if __name__ == "__main__":
    
    main()