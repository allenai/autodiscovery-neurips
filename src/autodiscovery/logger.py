import os
import json
from autogen import ChatCompletion

class TreeLogger:

    level: int
    agent_name: str
    node_idx: int

    def __init__(self, log_dir: str):
        """Initialize logger that stores logs for each node in a tree exploration.
        
        Args:
            log_dir: Directory to store all log files
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
    def log_node(self, level: int, node_idx: int, message: str | dict):
        """Log a message for a specific node.
        
        Args:
            level: Level of the node in the tree
            node_idx: Index of the node within its level
            message: Message to log (string or dictionary)
        """
        filename = os.path.join(self.log_dir, f"node_{level}_{node_idx}.json")
        
        with open(filename, 'a') as f:
            if isinstance(message, dict):
                f.write(json.dumps(message, indent=2))
            else:
                f.write(json.dumps(json.loads(message), indent=2))

    def load_node(self, level: int, node_idx: int, as_json: bool = False) -> list[str | dict]:
        """Load the contents of a log file for a specific node.
        
        Args:
            level: Level of the node in the tree
            node_idx: Index of the node within its level
            as_json: If True, attempt to parse lines as JSON. If False, return raw strings.
            
        Returns:
            List of messages from the log file. Each message is either a string or
            dictionary depending on how it was originally logged and the as_json flag.
            
        Raises:
            FileNotFoundError: If the log file does not exist
        """
        filename = os.path.join(self.log_dir, f"node_{level}_{node_idx}.json")
        
        messages = None
        with open(filename, 'r') as f:
            if as_json:
                messages = json.load(f)
            else:
                messages = f.read()
                    
        return messages
    
    def log_choices(self, chat_completion: ChatCompletion, as_json: bool = False):
        filename = os.path.join(self.log_dir, f"{self.agent_name}_{self.level}_{self.node_idx}.json")
        choice_log = []
        for choice in chat_completion.choices:
            msg = {
                "message": choice.message.content,
                "token_logprobs": self._parse_logprobs(choice.logprobs)
                }
            choice_log.append(msg)
        
        with open(filename, 'w') as f:
            json.dump(choice_log, f, indent=2)
            

        
        # with open(filename, 'a') as f:
        #     for choice in chat_completion.choices:
        #         f.write(choice.message.content + '\n')
    
    def _parse_logprobs(self, choice_logprobs):
        logprobs = []
        for token in choice_logprobs.content:
            token_prob = {
                "token": token.token,
                "bytes": token.bytes,
                "logprob": token.logprob
            }
            logprobs.append(token_prob)
        return logprobs