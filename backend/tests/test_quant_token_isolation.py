"""Quant tokens must not escape the institutional research API boundary."""
from unittest.mock import patch
from services.auth import auth_store
from services.institution import inst_store

def test_personal_auth_rejects_quant_before_user_lookup():
    with patch.object(auth_store, "dev_skip_auth", return_value=False), patch.object(auth_store, "decode_token", return_value={"sub":"7", "product":"quant"}), patch.object(auth_store, "get_user_by_id") as lookup:
        assert auth_store.user_from_authorization("Bearer fixture") is None
        lookup.assert_not_called()

def test_subjective_auth_rejects_quant_before_user_lookup():
    with patch.object(inst_store, "dev_skip_auth", return_value=False), patch.object(inst_store, "decode_token", return_value={"sub":"7", "scope":"inst", "product":"quant"}), patch.object(inst_store, "get_user_by_id") as lookup:
        assert inst_store.user_from_inst_authorization("Bearer fixture") is None
        lookup.assert_not_called()

def test_personal_auth_rejects_subjective_inst_scope_by_default():
    with patch.object(auth_store, "dev_skip_auth", return_value=False), patch.object(auth_store, "decode_token", return_value={"sub":"7", "scope":"inst"}), patch.object(auth_store, "get_user_by_id") as lookup:
        assert auth_store.user_from_authorization("Bearer fixture") is None
        lookup.assert_not_called()
        row = {"id":7,"status":"active","token_version":0}
        with patch.object(auth_store, "get_user_by_id", return_value=row), patch.object(auth_store, "_public_user", return_value={"id":7}):
            assert auth_store.user_from_authorization("Bearer fixture", allow_inst=True) == {"id":7}

def test_explicit_quant_identity_resolution_still_validates_token_version():
    row = {"id":7,"status":"active","token_version":2}
    with patch.object(auth_store, "dev_skip_auth", return_value=False), patch.object(auth_store, "decode_token", return_value={"sub":"7", "product":"quant","tv":1}), patch.object(auth_store,"get_user_by_id",return_value=row):
        assert auth_store.user_from_authorization("Bearer fixture",allow_quant=True) is None

def test_explicit_quant_resolution_and_original_personal_resolution_work():
    row = {"id":7,"status":"active","token_version":2}
    with patch.object(auth_store, "dev_skip_auth", return_value=False), patch.object(auth_store, "get_user_by_id",return_value=row), patch.object(auth_store,"_public_user",return_value={"id":7}):
        with patch.object(auth_store,"decode_token",return_value={"sub":"7","product":"quant","tv":2}):
            assert auth_store.user_from_authorization("Bearer fixture",allow_quant=True) == {"id":7}
        with patch.object(auth_store,"decode_token",return_value={"sub":"7","tv":2}):
            assert auth_store.user_from_authorization("Bearer fixture") == {"id":7}
