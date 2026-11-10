from app.modules.plaid.dedup import split_accounts

INS = "ins_1"


def ex(pid, mask, name="Checking", typ="depository", sub="checking", ins=INS, persistent=None):
    return {"plaid_account_id": pid, "mask": mask, "name": name, "type": typ, "subtype": sub,
            "institution_id": ins, "persistent_account_id": persistent}


def inc(aid, mask, name="Checking", typ="depository", sub="checking", persistent=None):
    return {"account_id": aid, "mask": mask, "name": name, "type": typ, "subtype": sub,
            "persistent_account_id": persistent}


def test_new_bank_all_new():
    new, dups = split_accounts([], [inc("a1", "0001")], INS)
    assert len(new) == 1 and not dups


def test_same_bank_again_all_duplicates():
    new, dups = split_accounts([ex("old1", "0001")], [inc("n1", "0001")], INS)
    assert not new and len(dups) == 1


def test_same_bank_with_one_extra_account():
    existing = [ex("old1", "0001")]
    new, dups = split_accounts(existing, [inc("n1", "0001"), inc("n2", "0002", "Savings", sub="savings")], INS)
    assert [a["account_id"] for a in new] == ["n2"] and len(dups) == 1


def test_two_distinct_accounts_same_institution_allowed():
    new, dups = split_accounts([ex("old1", "0001")], [inc("n1", "0002")], INS)
    assert len(new) == 1 and not dups


def test_same_mask_different_name_allowed():
    new, _ = split_accounts([ex("old1", "0001", "Checking")], [inc("n1", "0001", "Business Checking")], INS)
    assert len(new) == 1


def test_missing_institution_never_blocks():
    new, dups = split_accounts([ex("old1", "0001", ins=None)], [inc("n1", "0001")], None)
    assert len(new) == 1 and not dups


def test_missing_mask_never_blocks():
    new, _ = split_accounts([ex("old1", None)], [inc("n1", None)], INS)
    assert len(new) == 1


def test_persistent_id_is_decisive():
    new, dups = split_accounts([ex("old1", "0001", persistent="P1")], [inc("n1", "9999", persistent="P1")], INS)
    assert not new and len(dups) == 1
    new, dups = split_accounts([ex("old1", "0001", persistent="P1")], [inc("n1", "0001", persistent="P2")], INS)
    assert len(new) == 1


def test_replay_same_plaid_account_id_not_duplicate():
    new, dups = split_accounts([ex("same", "0001")], [inc("same", "0001")], INS)
    assert len(new) == 1 and not dups