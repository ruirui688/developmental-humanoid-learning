# GitHub SSH 密钥

本机已生成一把专用于本仓库 GitHub 操作的 Ed25519 密钥：

- 私钥：`/home/ubuntu/.ssh/github_developmental_humanoid_ed25519`
- 公钥：`/home/ubuntu/.ssh/github_developmental_humanoid_ed25519.pub`
- 指纹：`SHA256:xUT2JLLOz3601DaF3TjacouOA/YpPC60Um56909EndM`
- 注释：`github-developmental-humanoid-learning`

私钥没有写入仓库，也不能发送给任何人。当前密钥使用空口令生成；在多人或不受信任的机器上使用前，应重新生成带口令的密钥或使用 ssh-agent 保护私钥。

查看并复制公钥：

```bash
cat /home/ubuntu/.ssh/github_developmental_humanoid_ed25519.pub
```

在 GitHub 中打开 **Settings → SSH and GPG keys → New SSH key**，类型选择 **Authentication Key**，将上述公钥粘贴进去。添加后可在本机验证：

```bash
GIT_SSH_COMMAND='ssh -i /home/ubuntu/.ssh/github_developmental_humanoid_ed25519 -o IdentitiesOnly=yes' \
  ssh -T git@github.com
```

本仓库当前已配置为使用 SSH 远端：

```text
ssh://git@github.com/ruirui688/developmental-humanoid-learning.git
```

本机已通过只读 `git ls-remote origin HEAD refs/heads/main` 验证认证成功。远端 `main` 当前为 `6abcf26`；本地后续提交尚未推送。没有执行 push。
