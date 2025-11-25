# 📘 README — Faza 1  
# Priprema Visual Studio Code-a za rad u Docker kontejneru

Ovaj dokument opisuje precizne korake potrebne da se Visual Studio Code pripremi za rad unutar Docker kontejnera.

---

## 1. Instaliraj Docker Desktop
```markdown
1. Preuzmi Docker Desktop za macOS (Apple Silicon ili Intel).
2. Instaliraj aplikaciju.
3. Pokreni Docker Desktop.
4. Provjeri da Docker radi:

```bash
docker run hello-world
```
```

---

## 2. Instaliraj Visual Studio Code
```markdown
1. Preuzmi Visual Studio Code sa službene stranice.
2. Instaliraj i pokreni.
```

---

## 3. Instaliraj potrebne VS Code ekstenzije
```markdown
U VS Code-u otvori Extensions i instaliraj:

Obavezno:
- Dev Containers (Microsoft)

Preporučeno:
- Docker (Microsoft)

Opcionalno:
- C/C++ (Microsoft)
- CMake Tools
```

---

## 4. Provjeri da VS Code prepoznaje Docker
```markdown
Docker Desktop mora biti pokrenut.

Provjera u terminalu:
```bash
docker ps
```

Ako naredba radi bez errora → Docker radi ispravno.

VS Code ne smije prikazivati:
- Docker not found
- Cannot connect to Docker daemon
```

---

## 5. Kreiraj radni direktorij
```markdown
U terminalu:

```bash
mkdir -p ~/Projects/MyDockerProject
cd ~/Projects/MyDockerProject
```

Zatim otvori folder u VS Code-u:

File → Open Folder → MyDockerProject
```
