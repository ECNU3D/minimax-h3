"""Agent-facing deterministic validation; it never repairs or saves a project."""
import json
import sys
from .importer import apply_parse

def validate(payload):
    candidate=dict(payload['result']); candidate.pop('audit',None)
    try:
        apply_parse({},payload['source'],candidate)
        return {'ok':True}
    except (ValueError,KeyError,TypeError,IndexError) as error:
        return {'ok':False,'error':str(error)}

if __name__=='__main__':
    print(json.dumps(validate(json.load(sys.stdin)),ensure_ascii=False))
