# Publishing this repo to GitHub

Two paths — pick the one that matches what you have installed.

## Path A: Using GitHub CLI (`gh`) — fastest

### One-time setup
1. Install GitHub CLI from https://cli.github.com — works on Windows/Mac/Linux
2. In PowerShell:
   ```powershell
   gh auth login
   ```
   Pick "GitHub.com" → "HTTPS" → "Login with web browser" → paste the code in your browser.

### Publish the repo (run from this folder)
```powershell
cd C:\Users\Jeff\Desktop\lead-scraper-toolkit   # or wherever you put the folder
git init
git add .
git commit -m "Initial commit — lead scraper + data kit"
gh repo create lead-scraper-toolkit --public --source=. --push
```

Last line creates the GitHub repo, links it, and pushes. You're done — go look at it on github.com.

## Path B: Plain git + GitHub website

### One-time setup
1. Install Git for Windows from https://git-scm.com/download/win
2. Create a GitHub account at https://github.com if you don't have one
3. Open PowerShell and set your identity:
   ```powershell
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```

### Publish
1. Go to https://github.com/new
2. Repo name: `lead-scraper-toolkit`
3. Pick **Public** or **Private** (Private = only you can see it)
4. Leave everything else unchecked (no README, no .gitignore — we have those)
5. Click **Create repository**
6. GitHub shows you a page with commands. Copy the section under "…or push an existing repository from the command line" — it looks like:
   ```
   git remote add origin https://github.com/YOUR-USERNAME/lead-scraper-toolkit.git
   git branch -M main
   git push -u origin main
   ```

7. In PowerShell:
   ```powershell
   cd C:\Users\Jeff\Desktop\lead-scraper-toolkit
   git init
   git add .
   git commit -m "Initial commit — lead scraper + data kit"
   # Then paste the three lines from step 6 above
   ```

8. First push will pop up a browser for GitHub auth. Approve it. Done.

## Pulling it into Claude Code

Once it's on GitHub, from any machine with Claude Code:

```powershell
cd C:\Users\Jeff\Desktop
git clone https://github.com/YOUR-USERNAME/lead-scraper-toolkit.git
cd lead-scraper-toolkit
claude
> Read README.md, then the data-kit folder. Help me run the download and build the lead-gen project.
```

## Making changes later
Whenever you tweak something locally and want to update GitHub:
```powershell
git add .
git commit -m "describe what you changed"
git push
```

## Cloning on another machine
```powershell
git clone https://github.com/YOUR-USERNAME/lead-scraper-toolkit.git
```
That's it — full copy, runnable immediately.
