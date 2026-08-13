"""
Fix the ragas <-> langchain-community incompatibility.

ragas imports `langchain_community.chat_models.vertexai.ChatVertexAI`, which was
removed in langchain-community 0.4.x. ragas uses it only in an isinstance list
(MULTIPLE_COMPLETION_SUPPORTED) to decide whether a model supports n-completions.
A Groq model is never an instance of it, so a stub restores the import with no
behavioural change.

Run this INSIDE the ragas virtualenv:
    python fix_ragas_vertexai.py
"""
import os
import sys

SHIM = '''"""
Compatibility shim created for ragas.

`langchain_community.chat_models.vertexai` was removed in langchain-community
0.4.x, but ragas still imports ChatVertexAI from it. ragas only uses the symbol
in an isinstance() check, so this placeholder restores the import. It is NOT a
working Vertex AI client -- instantiating it raises.
"""

class ChatVertexAI:  # pragma: no cover - placeholder only
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ChatVertexAI is a compatibility stub and cannot be instantiated. "
            "Install langchain-google-vertexai if you need real Vertex AI support."
        )


__all__ = ["ChatVertexAI"]
'''


def main():
    try:
        import langchain_community
    except ImportError:
        sys.exit("langchain_community not installed - activate the ragas venv first.")

    pkg = os.path.dirname(langchain_community.__file__)
    target_dir = os.path.join(pkg, "chat_models")
    target = os.path.join(target_dir, "vertexai.py")

    if not os.path.isdir(target_dir):
        sys.exit(f"Unexpected layout: {target_dir} does not exist.")

    if os.path.exists(target):
        print(f"Already present, leaving alone: {target}")
    else:
        with open(target, "w") as f:
            f.write(SHIM)
        print(f"Wrote shim: {target}")

    # verify
    for mod in list(sys.modules):
        if mod.startswith(("ragas", "langchain_community")):
            del sys.modules[mod]
    try:
        import ragas
        print(f"ragas imports OK (version {ragas.__version__})")
    except Exception as e:
        sys.exit(f"ragas still failing: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
