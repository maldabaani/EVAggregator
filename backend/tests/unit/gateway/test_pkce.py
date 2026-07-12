from evagg.gateway.pkce import compute_code_challenge, verify_code_verifier


def test_matching_verifier_and_challenge_pass():
    verifier = "a" * 43
    challenge = compute_code_challenge(verifier)
    assert verify_code_verifier(verifier, challenge)


def test_mismatched_verifier_fails():
    challenge = compute_code_challenge("a" * 43)
    assert not verify_code_verifier("b" * 43, challenge)
