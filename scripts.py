import os
import requests
import zipfile
import tempfile
import argparse
import subprocess
from contextlib import contextmanager


DEFAULT_REPOSITORIES = [
    "WebAssembly/wasi-clocks",
    "WebAssembly/wasi-io",
    "WebAssembly/wasi-filesystem",
    "WebAssembly/wasi-random",
    "WebAssembly/wasi-sockets",
]

@contextmanager
def change_directory(destination):
    """安全切换目录的上下文管理器"""
    original_dir = os.getcwd()
    try:
        os.chdir(destination)
        yield
    finally:
        os.chdir(original_dir)

def get_latest_release(repo_name, github_token=None):
    """获取指定仓库的最新release"""
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    release_data = response.json()
    
    if not release_data:
        raise Exception(f"No releases found for {repo_name}")
    
    return {
        "zip_url": release_data["zipball_url"],
        "tag_name": release_data["tag_name"]
    }
def download_and_extract_release(zip_url, target_dir, expected_repo_name):
    """下载并解压release的zip文件"""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
        try:
            response = requests.get(zip_url, stream=True)
            response.raise_for_status()
            
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file.close()
            
            with zipfile.ZipFile(temp_file.name, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            
            # 检查解压后的文件夹名是否包含预期的仓库名
            extracted_dirs = os.listdir(target_dir)
            extracted_dir = None

            for dir_name in extracted_dirs:
                full_path = os.path.join(target_dir, dir_name)
                if os.path.isdir(full_path):  # 确保是目录
                    # 检查是否包含预期的仓库名（支持 - 和 _ 转换）
                    repo_variations = [
                        expected_repo_name.lower(),
                        expected_repo_name.replace('-', '_').lower(),
                        expected_repo_name.replace('_', '-').lower()
                    ]
                    
                    if any(variation in dir_name.lower() for variation in repo_variations):
                        extracted_dir = full_path
                        break

            if extracted_dir is None:
                raise ValueError(f"No matching folder found for expected repo '{expected_repo_name}' in extracted directories: {extracted_dirs}")
            
            return extracted_dir
        finally:
            os.unlink(temp_file.name)

def run_moon_commands(package_dir):
    """在package目录中运行moon命令"""
    try:
        with change_directory(package_dir):
            print(f"Running 'moon install' in {package_dir}")
            fmt_result = subprocess.run(
                ["moon", "install"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(fmt_result.stdout)
    
            print(f"Running 'moon fmt' in {package_dir}")
            fmt_result = subprocess.run(
                ["moon", "fmt"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(fmt_result.stdout)
            
            print(f"Running 'moon info' in {package_dir}")
            info_result = subprocess.run(
                ["moon", "info"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(info_result.stdout)
            return True
    except subprocess.CalledProcessError as e:
        print(f"Moon command failed: {e.stderr}")
        return False

def process_repositories(repo_list, github_token=None):
    """处理仓库列表"""
    os.makedirs("wits", exist_ok=True)
    os.makedirs("packages", exist_ok=True)
    
    for full_repo_name in repo_list:
        try:
            repo_name = full_repo_name.split('/')[-1]
            print(f"\nProcessing repository: {full_repo_name} (using name: {repo_name})")
            
            release = get_latest_release(full_repo_name, github_token)
            print(f"Found release: {release['tag_name']}")
            
            extracted_dir = download_and_extract_release(release["zip_url"], "wits", repo_name)
            print(f"Extracted to: {extracted_dir}")
            
            # 确保wit目录存在
            wit_path = os.path.join(extracted_dir, "wit")
            if not os.path.exists(wit_path):
                raise FileNotFoundError(f"WIT directory not found at {wit_path}")
            
            out_dir = os.path.join("packages", repo_name)
            os.makedirs(out_dir, exist_ok=True)
            
            print(f"Running cargo command on: {wit_path}")
            cargo_result = subprocess.run(
                ["cargo", "run", "moonbit", wit_path, "--out-dir", out_dir, "--world", "imports"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(cargo_result.stdout)
            
            print(f"Running moon commands in {out_dir}")
            moon_success = run_moon_commands(out_dir)
            
            print(f"Successfully processed {full_repo_name}" if moon_success 
                 else f"Processed {full_repo_name} but moon commands failed")
                
        except Exception as e:
            print(f"Error processing {full_repo_name}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Process GitHub repositories and run cargo/moon commands")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--repos", nargs="+", help="List of GitHub repositories in 'owner/repo' format")
    group.add_argument("--from-const", action="store_true", help="Use the default constant repository list")
    parser.add_argument("--token", help="GitHub personal access token (optional)", default=None)
    
    args = parser.parse_args()
    
    repo_list = DEFAULT_REPOSITORIES if args.from_const else args.repos
    if not repo_list:
        parser.error("You must provide either --repos list or --from-const flag")
    
    print(f"Using repository list: {repo_list}")
    process_repositories(repo_list, args.token)

if __name__ == "__main__":
    main()