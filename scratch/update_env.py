import os
import sys

def update_env_variable(key: str, value: str, env_file: str = ".env"):
    """
    Updates or adds a variable in the .env file securely.
    """
    lines = []
    updated = False
    
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    with open(env_file, "w") as f:
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                updated = True
            else:
                f.write(line)
                
        if not updated:
            f.write(f"{key}={value}\n")
            
    print(f"Successfully updated {key} in {env_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python update_env.py <KEY> <VALUE>")
        sys.exit(1)
        
    update_env_variable(sys.argv[1], sys.argv[2])
