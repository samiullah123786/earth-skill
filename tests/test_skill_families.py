"""One craft, many private variants: only the parent is anybody else's business."""
from __future__ import annotations

from earth_cli.shareability import group_families, parent_guidance, plan_deposits


def test_the_case_this_was_built_for():
    """scriptwriting for two channels is three skills and one shareable craft."""
    plan = plan_deposits(['scriptwriting', 'channel-a-scriptwriting', 'channel-b-scriptwriting'])
    assert plan.deposit == ['scriptwriting']
    assert plan.covered_by_parent == {
        'channel-a-scriptwriting': 'scriptwriting',
        'channel-b-scriptwriting': 'scriptwriting',
    }
    assert 'twice' in plan.reason_for('channel-a-scriptwriting')


def test_daughters_with_no_parent_ask_for_one_to_be_written():
    """Only when the privacy check actually found a subject inside them."""
    plan = plan_deposits(
        ['pawtold-scriptwriter', 'acme-scriptwriter'],
        wrappers=['pawtold-scriptwriter', 'acme-scriptwriter'],
    )
    assert plan.deposit == []
    assert plan.write_parent_first == {'scriptwriter': ['acme-scriptwriter', 'pawtold-scriptwriter']}
    steps = parent_guidance('scriptwriter', ['pawtold-scriptwriter'])
    assert any('no client, channel or product' in step for step in steps)
    assert any('stay on this machine' in step for step in steps)


def test_a_hyphen_alone_never_demands_a_parent_be_invented():
    """competitor-analysis has the shape of pawtold-scriptwriter and is not it.

    The leading word describes the work rather than naming a client, and no
    amount of name-shape reasoning can tell those apart - so nothing is asked
    of a skill the privacy check did not flag.
    """
    plan = plan_deposits(['competitor-analysis', 'keyword-research'])
    assert plan.write_parent_first == {}
    assert sorted(plan.deposit) == ['competitor-analysis', 'keyword-research']


def test_unrelated_skills_are_left_alone():
    names = ['deslop', 'bento', 'gsap-core', 'framer-motion']
    plan = plan_deposits(names)
    assert sorted(plan.deposit) == sorted(names)
    assert plan.covered_by_parent == {}
    assert plan.write_parent_first == {}


def test_a_generic_two_word_name_is_not_a_daughter():
    """python-developer names a craft twice; it names nobody."""
    plan = plan_deposits(['python-developer', 'video-editor'])
    assert sorted(plan.deposit) == ['python-developer', 'video-editor']
    assert plan.covered_by_parent == {}


def test_the_privacy_verdict_still_wins():
    """A parent that is itself private is not deposited just for being a parent."""
    plan = plan_deposits(
        ['scriptwriting', 'channel-a-scriptwriting'],
        shareable=[],                       # nothing passed the privacy check
    )
    assert plan.deposit == []
    # The daughter is still held back, for its own separate reason.
    assert plan.covered_by_parent == {'channel-a-scriptwriting': 'scriptwriting'}


def test_families_are_keyed_on_the_craft():
    families = group_families(['scriptwriting', 'channel-a-scriptwriting', 'deslop'])
    assert set(families) == {'scriptwriting'}
    family = families['scriptwriting']
    assert family.parent == 'scriptwriting'
    assert family.daughters == ['channel-a-scriptwriting']
    assert family.needs_a_parent is False


def test_a_family_with_only_daughters_knows_it_needs_a_parent():
    families = group_families(['channel-a-scriptwriting', 'channel-b-scriptwriting'])
    assert families['scriptwriting'].needs_a_parent is True


def test_ing_and_er_forms_are_both_understood():
    """People name a skill scriptwriting as often as scriptwriter."""
    for craft in ('scriptwriting', 'scriptwriter', 'copywriting', 'editor'):
        plan = plan_deposits([craft, f'acme-{craft}'])
        assert plan.deposit == [craft], craft
        assert plan.covered_by_parent == {f'acme-{craft}': craft}, craft


def test_the_craft_list_stays_narrow_on_purpose():
    """A craft word must not be the ordinary tail of an innocent name.

    "analysis" and "research" were in this list once, and competitor-analysis
    and keyword-research were immediately treated as somebody's private client
    work. Anything added here has to fail this test's spirit, not just its
    letter.
    """
    for innocent in ('competitor-analysis', 'keyword-research', 'link-prospecting',
                     'competitive-landscape', 'animation-runtime', 'seo-audit'):
        plan = plan_deposits([innocent])
        assert plan.deposit == [innocent], innocent
        assert plan.covered_by_parent == {}, innocent
