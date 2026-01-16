import os
import json
import re
from beliefs import evaluate_hypothesis_distribution

def load_node_logs(directory, level=None, node_idx=None):
    """
    Loads and parses log files in a directory that match the format
    'node_level_index.json', saving the contents in a dictionary.

    Args:
        directory (str): The path to the directory.
        level (int, optional): The level of the node in the tree. If provided, only logs for this level are loaded.
        node_idx (int, optional): The index of the node within its level. If provided, only logs for this node are loaded.

    Returns:
        dict: A dictionary where keys are tuples (index, level) and values
              are the contents of the log files. Returns an empty dict if
              no matching files are found or an error occurs.
    """
    result = {}
    try:
        for filename in os.listdir(directory):
            match = re.match(r"node_(\d+)_(\d+)\.json", filename)  # Updated extension
            if match:
                file_level = int(match.group(1))
                file_index = int(match.group(2))
                if (level is not None and file_level != level) or (node_idx is not None and file_index != node_idx):
                    continue
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, "r") as f:
                        log_content = json.load(f)  # Read the entire log file
                        result[(file_level, file_index)] = extract_node_messages(log_content)
                except OSError as e:
                    print(f"Error reading {filename}: {e}")
        return result
    except FileNotFoundError:
        print(f"Directory not found: {directory}")
        return {}
    except OSError as e:
        print(f"OS error occurred: {e}")
        return {}


def extract_node_messages(json_data):
    """
    Extracts messages starting from the last occurrence of
    a message with role 'user_proxy'.

    Args:
        json_data (list): A list of dictionaries representing JSON data.

    Returns:
        list: A list of dictionaries containing messages from the last 'user_proxy'
              message onwards. Returns an empty list if no 'user_proxy' messages
              are found.
    """
    if not isinstance(json_data, list):
        return []

    user_proxy_indices = [i for i, msg in enumerate(json_data) if msg.get("name") == "user_proxy"]

    if not user_proxy_indices:
        return []

    last_user_proxy_index = user_proxy_indices[-1]
    return json_data[last_user_proxy_index:]

def extract_hypotheses_from_logs(messages):
    """
    Extracts hypotheses from a list of messages.

    Args:
        messages (list): A list of message dictionaries

    Returns:
        list: List of extracted hypotheses
    """
    hypotheses = []
    for msg in messages:
        if msg.get("name") == "hypothesis_generator":
            try:
                content = json.loads(msg.get("content", "{}"))
                if "hypothesis" in content:
                    hypotheses.append(content["hypothesis"])
            except (json.JSONDecodeError, TypeError):
                continue
    return hypotheses

def save_belief_distribution(log_dirname, level, node_idx, messages, current_hypothesis, context, distribution,
                             model="gpt-4o", n_samples=30, is_prior=False, temperature=None):
    """Save belief distribution with messages in proper JSON format.
    
    Args:
        log_dirname (str): Directory where belief logs are stored
        level (int): Tree level of the current node
        node_idx (int): Index of the current node within its level
        messages (list): List of message dicts containing hypotheses and evidence
        current_hypothesis (str): The hypothesis being evaluated
        context (str): Context type - one of "current", "branch", or "all"
        distribution (str): Distribution type - either "prior" or "posterior"
    """
    belief_result = evaluate_hypothesis_distribution(
        messages=messages,
        hypothesis=current_hypothesis,
        n_samples=n_samples,
        temperature=temperature,
        is_prior=is_prior,
        model=model
    )

    belief_record = {
        "belief_result": json.loads(belief_result.model_dump_json()),
        "context": context,
        "messages": messages,
        "distribution": distribution,
        "current_hypothesis": current_hypothesis
    }

    belief_log_filename = os.path.join(log_dirname, f"belief_{level}_{node_idx}.json")
    
    try:
        with open(belief_log_filename, 'r') as f:
            records = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        records = []
        
    records.append(belief_record)
    with open(belief_log_filename, 'w') as f:
        json.dump(records, f, indent=2)

def load_parent_hypotheses(log_dirname, level, parent_node_idx, context_type="branch"):
    """Load hypotheses from parent node's belief logs based on context type.
    
    Args:
        log_dirname (str): Directory where belief logs are stored
        level (int): Current tree level (parent will be level-1) 
        parent_node_idx (int): Index of the parent node
        context_type (str): Context to load - one of "current", "branch", or "all"
    
    Returns:
        list: List of dicts containing hypotheses and their beliefs from the parent node
    """
    if parent_node_idx is None:
        return []
        
    parent_log_filename = os.path.join(log_dirname, f"belief_{level-1}_{parent_node_idx}.json")
    if not os.path.exists(parent_log_filename):
        return []

    try:
        with open(parent_log_filename, 'r') as f:
            records = json.load(f)
    except json.JSONDecodeError:
        return []

    # Find latest posterior belief record with matching context
    matching_records = [r for r in records 
                      if r["distribution"] == "posterior" and 
                      r["context"] == context_type]
    
    if not matching_records:
        return []
        
    latest_record = matching_records[-1]
    
    hypotheses = []
    for msg in latest_record["messages"]:
        if msg.get("name") == "my_hypotheses":
            try:
                content = json.loads(msg["content"])
                if "hypothesis" in content:
                    hypotheses.append({
                        "hypothesis": content["hypothesis"],
                        "belief": content.get("belief")
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    # Set belief for latest hypothesis from belief result
    if hypotheses:
        hypotheses[-1]["belief"] = latest_record["belief_result"]["believes_hypothesis"]
    
    return hypotheses

def get_current_hypothesis_and_evidence(node_logs):
    """Extract current hypothesis and evidence from node logs.
        
    Returns:
        tuple: (current_hypothesis, evidence_messages) where:
            - current_hypothesis (str): The latest hypothesis generated
            - evidence_messages (list): All messages from the current node interaction
    """
    if not node_logs:
        return None, []
        
    messages = next(iter(node_logs.values()))
    
    # Find last user_proxy message by iterating in reverse
    start_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("name") == "user_proxy":
            start_idx = i
            break
            
    if start_idx is None:
        return None, []
        
    node_messages = messages[start_idx:]
    
    # Find first hypothesis in node_messages
    current_hypothesis = None
    for msg in node_messages:
        if msg.get("name") == "hypothesis_generator":
            try:
                content = json.loads(msg["content"])
                current_hypothesis = content.get("hypothesis")
                if current_hypothesis:
                    break
            except (json.JSONDecodeError, TypeError):
                continue
                
    return current_hypothesis, node_messages

def load_all_hypotheses(log_dirname):
    """Load all hypotheses and their beliefs from all belief log files.
    
    Args:
        log_dirname (str): Directory where belief logs are stored
        
    Returns:
        list: List of dicts containing hypotheses and their beliefs from all nodes
    """
    all_hypotheses = []
    
    try:
        for filename in os.listdir(log_dirname):
            if not filename.startswith("belief_") or not filename.endswith(".json"):
                continue
                
            try:
                level, node_idx = map(int, filename[7:-5].split("_"))
            except ValueError:
                continue
                
            filepath = os.path.join(log_dirname, filename)
            try:
                with open(filepath, 'r') as f:
                    records = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
                
            # Find latest posterior belief record with context "all"
            matching_records = [r for r in records 
                             if r["distribution"] == "posterior" and 
                             r["context"] == "all"]
            
            if not matching_records:
                continue
                
            latest_record = matching_records[-1]
            
            all_hypotheses.append({
                "hypothesis": latest_record["current_hypothesis"],
                "belief": latest_record["belief_result"]["believes_hypothesis"],
                # "level": level,
                # "node_idx": node_idx
            })
    
    except OSError:
        return []
        
    return all_hypotheses