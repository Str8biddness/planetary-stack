#!/usr/bin/env python3
import sys
import requests
import json

def get_ai_analysis(command, exit_code):
    # Connect to DeepSeek API
    api_key = "your_deepseek_api_key_here"  # You'll set this later
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    prompt = f"Analyze this terminal command: '{command}' that exited with code {exit_code}. Provide brief, helpful insight."
    
    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json={"model": "deepseek-coder", "messages": [{"role": "user", "content": prompt}]}
        )
        return response.json()['choices'][0]['message']['content']
    except:
        return "AI analysis temporarily unavailable"
    
if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "no command"
    exit_code = sys.argv[2] if len(sys.argv) > 2 else "0"
    print(get_ai_analysis(command, exit_code))
