import drill


def test_drill_prompt_follows_the_strain_and_forbids_real_identifiers():
    strain = {"scamType": "digital_arrest", "impersonatedEntity": "CBI", "steps": ["Claims a parcel was caught.",
              "Threatens arrest."], "redFlags": ["a", "b", "c"]}
    prompt = drill.build_drill_prompt(strain, "Amma")
    assert "1. Claims a parcel was caught." in prompt and "2. Threatens arrest." in prompt
    assert "Never ask for a real OTP" in prompt
    assert "reach_payment_demand" in prompt


def test_coach_cue_names_the_three_red_flags_and_the_reason():
    strain = {"redFlags": ["flag one", "flag two", "flag three", "flag four"]}
    cue = drill.coach_cue(strain, "Papa", "user_shared_details")
    assert "flag one" in cue and "flag three" in cue and "flag four" not in cue
    assert "started to share numbers" in cue


def test_new_drill_requires_consent_flag_set_by_construction():
    doc = drill.new_drill_doc(owner="o", strain_id="s", parent_name="Asha", parent_title="Amma", family_name="Ravi")
    assert doc["consentGiven"] is True and doc["status"] == "created"
    assert len(doc["shareKey"]) >= 12
