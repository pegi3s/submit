"""
Patches FileSelectorComponent.restoreGithubPrefs() to read URL query
parameters (repo, branch, token, author, email) so the page can be
pre-filled when opened with a crafted URL from Streamlit.
"""

import sys

PATH = (
    "/opt/bdip-web-manager/src/app/components/"
    "file-selector/file-selector.component.ts"
)

OLD = """\
  private restoreGithubPrefs(): void {
    if (!this.isBrowser()) return;

    const token = this.readSessionValue(this.storageKeys.githubToken);
    const authorName = this.readLocalValue(this.storageKeys.githubAuthorName);
    const authorEmail = this.readLocalValue(this.storageKeys.githubAuthorEmail);

    if (token) this.githubToken.set(token);
    if (authorName) this.githubAuthorName.set(authorName);
    if (authorEmail) this.githubAuthorEmail.set(authorEmail);
  }\
"""

NEW = """\
  private restoreGithubPrefs(): void {
    if (!this.isBrowser()) return;

    // URL query params take priority (allows pre-filling from Streamlit)
    const params = new URLSearchParams(window.location.search);

    const repo   = params.get('repo');
    const branch = params.get('branch');
    const token  = params.get('token')  || this.readSessionValue(this.storageKeys.githubToken);
    const author = params.get('author') || this.readLocalValue(this.storageKeys.githubAuthorName);
    const email  = params.get('email')  || this.readLocalValue(this.storageKeys.githubAuthorEmail);

    if (repo)   this.githubRepo.set(repo);
    if (branch) this.githubBranch.set(branch);
    if (token)  this.githubToken.set(token);
    if (author) this.githubAuthorName.set(author);
    if (email)  this.githubAuthorEmail.set(email);
  }\
"""

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

if OLD not in src:
    print("ERROR: pattern not found in source file.", file=sys.stderr)
    print("First 200 chars of file:", repr(src[:200]), file=sys.stderr)
    sys.exit(1)

src = src.replace(OLD, NEW, 1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("Patch applied successfully.")
