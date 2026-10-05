import copy
import os
import tempfile

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

os.environ.setdefault("EVIDENCE_CACHE", tempfile.mkdtemp(prefix="cc-evidence-"))

DEV = Account.from_key("0x" + "11" * 32)
DEV2 = Account.from_key("0x" + "22" * 32)


def box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def make_claim(project_id="TEST-A", boundary=None, vintage=2023, credits=10_000, developer=DEV, ptype="avoided_deforestation"):
    return {
        "projectId": project_id,
        "developer": developer.address,
        "projectType": ptype,
        "vintageYear": vintage,
        "claimedCredits": credits,
        "boundary": copy.deepcopy(boundary or box(-63.10, -9.90, -63.05, -9.85)),
        "dataLabel": "synthetic",
    }


def sign(typed: dict | None, account=DEV) -> str:
    if typed is None:  # offline mode: no chain to bind a signature to; any well-formed one is accepted
        return "0x" + "ab" * 65
    msg = encode_typed_data(domain_data=typed["domain"], message_types=typed["types"], message_data=typed["message"])
    return "0x" + account.sign_message(msg).signature.hex().removeprefix("0x")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.sqlite3")
