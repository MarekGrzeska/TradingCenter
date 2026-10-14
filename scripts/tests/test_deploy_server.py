"""move-from-azure-to-vps, `vps-deployment`: the server as code. What is checked here is what would be expensive to find
out on the machine — a key that can run anything, a password that works over SSH, a file the play copies that is not
there — not what Ansible or cloud-init do with the words."""

from __future__ import annotations

import pathlib
import re

import yaml

DEPLOY = pathlib.Path(__file__).resolve().parent.parent.parent / "deploy"
CLOUD_INIT = yaml.safe_load((DEPLOY / "cloud-init.yaml").read_text(encoding="utf-8"))
PLAY = yaml.safe_load((DEPLOY / "ansible" / "site.yml").read_text(encoding="utf-8"))[0]


def sshd_policy() -> str:
    files = {f["path"]: f["content"] for f in CLOUD_INIT["write_files"]}
    return files["/etc/ssh/sshd_config.d/10-tradingcenter.conf"]


def test_nobody_logs_in_with_a_password_or_as_root() -> None:
    assert CLOUD_INIT["disable_root"] is True
    assert CLOUD_INIT["ssh_pwauth"] is False
    policy = sshd_policy()
    assert "PermitRootLogin no" in policy
    assert "PasswordAuthentication no" in policy
    assert re.search(r"^AllowUsers operator deploy tcbackup$", policy, re.MULTILINE)


def test_no_user_has_a_password() -> None:
    assert all(user["lock_passwd"] is True for user in CLOUD_INIT["users"])


def test_the_operators_key_is_a_placeholder_until_a_real_one_is_put_in() -> None:
    operator = next(u for u in CLOUD_INIT["users"] if u["name"] == "operator")
    assert all("REPLACE_WITH" in key for key in operator["ssh_authorized_keys"])


def test_the_deploying_user_has_no_key_of_its_own_in_cloud_init() -> None:
    """Its key is the restricted one the play writes; one here would be unrestricted."""
    deploy = next(u for u in CLOUD_INIT["users"] if u["name"] == "deploy")
    assert deploy["ssh_authorized_keys"] == []
    assert "sudo" not in deploy


def test_the_backup_user_has_no_key_of_its_own_in_cloud_init_and_no_docker() -> None:
    backup = next(u for u in CLOUD_INIT["users"] if u["name"] == "tcbackup")
    assert backup["ssh_authorized_keys"] == []
    assert "groups" not in backup and "sudo" not in backup


def _task(name_part: str) -> dict:
    return next(t for t in PLAY["tasks"] if name_part in t["name"])


def test_the_deploy_key_runs_one_command_and_nothing_else() -> None:
    options = _task("deploy key")["ansible.builtin.authorized_key"]["key_options"]
    assert options.startswith('command="')
    for restriction in ("no-port-forwarding", "no-agent-forwarding", "no-pty", "no-X11-forwarding"):
        assert restriction in options
    assert _task("deploy key")["ansible.builtin.authorized_key"]["exclusive"] is True


def test_the_firewall_denies_by_default_and_opens_only_the_proxy_and_named_ssh_sources() -> None:
    tasks = [t for t in PLAY["tasks"] if "community.general.ufw" in t]
    rules = [t["community.general.ufw"] for t in tasks]
    assert any(r.get("default") == "deny" and r.get("direction") == "incoming" for r in rules)
    opened = set()
    for task in tasks:
        rule = task["community.general.ufw"]
        if rule.get("rule") != "allow":
            continue
        # A loop over ports stands for each of them; a loop over sources (SSH) is one rule about port 22.
        ports = task["loop"] if str(rule["port"]) == "{{ item }}" else [rule["port"]]
        opened |= {(str(port), rule.get("proto")) for port in ports}
    assert opened == {("80", "tcp"), ("443", "tcp"), ("443", "udp"), ("22", "tcp")}
    ssh = next(r for r in rules if str(r.get("port")) == "22")
    assert "from_ip" in ssh, "SSH must name a source"
    assert PLAY["vars"]["ssh_allowed_cidrs"] == [], "nobody is let in until the operator names a source"


def test_every_file_the_play_seeds_exists() -> None:
    copy = _task("seeded")["ansible.builtin.copy"]
    missing = [
        item["src"]
        for item in _task("seeded")["loop"]
        if not (DEPLOY / "ansible" / item["src"]).resolve().exists()
    ]
    assert missing == []
    assert copy["owner"] == "deploy"


def test_the_deploy_key_reaches_the_script_the_play_installs() -> None:
    options = _task("deploy key")["ansible.builtin.authorized_key"]["key_options"]
    installed = {item["dest"] for item in _task("seeded")["loop"]}
    assert "bin/deploy" in installed
    assert PLAY["vars"]["deploy_command"] == "{{ app_dir }}/bin/deploy"
    assert "deploy_command" in options


def test_the_play_holds_no_secret() -> None:
    text = (DEPLOY / "ansible" / "site.yml").read_text(encoding="utf-8")
    # `password: "!"` is the opposite of a secret: it locks the account's password.
    assert not re.search(r'(password|token|secret)\s*[:=]\s*(?!"!")\S', text, re.IGNORECASE)


def test_the_backup_key_runs_the_read_only_window_and_nothing_else() -> None:
    key = _task("backup key")["ansible.builtin.authorized_key"]
    assert key["user"] == "tcbackup"
    assert key["key_options"].startswith('command="/usr/local/bin/tc-backup-serve"')
    for restriction in ("no-port-forwarding", "no-agent-forwarding", "no-pty", "no-X11-forwarding"):
        assert restriction in key["key_options"]
    assert key["exclusive"] is True


def test_the_script_the_backup_key_runs_is_roots_to_change() -> None:
    copy = _task("window onto the dumps")["ansible.builtin.copy"]
    assert (copy["owner"], copy["dest"]) == ("root", "/usr/local/bin/tc-backup-serve")


def test_the_dumps_are_readable_by_the_backup_group_only() -> None:
    directory = _task("Dumps")["ansible.builtin.file"]
    assert (directory["owner"], directory["group"], directory["mode"]) == ("deploy", "tcbackup", "2750")


def test_the_nightly_dump_and_the_morning_check_are_scheduled() -> None:
    jobs = {t["ansible.builtin.cron"]["name"] for t in PLAY["tasks"] if "ansible.builtin.cron" in t}
    assert {"tradingcenter backup", "tradingcenter backup check"} <= jobs
