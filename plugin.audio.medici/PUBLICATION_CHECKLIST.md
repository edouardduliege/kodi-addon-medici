# PUBLICATION_CHECKLIST.md

## 1. Structure du dépôt
- [ ] Le dossier de l’addon s’appelle exactement `plugin.audio.medici`
- [ ] `README.md` à la racine du repo
- [ ] `LICENSE` à la racine du repo
- [ ] `.gitignore` à la racine
- [ ] Aucun fichier inutile (`__pycache__`, `.pyc`, ZIP de release, etc.)
- [ ] Aucun token, mot de passe ou donnée de compte dans le dépôt
- [ ] Aucun dossier vide inutile (`settings/` supprimé)

## 2. `addon.xml`
- [ ] `id="plugin.audio.medici"`
- [ ] `provider-name="Édouard Duliège"`
- [ ] Version cohérente avec la release
- [ ] `<provides>audio video</provides>`
- [ ] Dépendances Kodi correctes
- [ ] `script.module.requests` déclaré
- [ ] Résumé EN correct
- [ ] Description EN correcte
- [ ] Disclaimer clair : addon non officiel, non affilié / non approuvé par Medici.tv
- [ ] Licence correcte
- [ ] Ajouter la source publique du code si nécessaire pour le repo Kodi

## 3. Fonctionnalités
- [ ] Login Medici.tv
- [ ] Cache du token
- [ ] Refresh token sur `401/403`
- [ ] Favoris existants visibles
- [ ] Concerts
- [ ] Opéras
- [ ] Ballets
- [ ] Documentaires
- [ ] Master classes
- [ ] Jazz
- [ ] Recherche
- [ ] Pagination
- [ ] Mode audio-only
- [ ] Mode audio + vidéo
- [ ] Choix qualité vidéo
- [ ] Auto limité à 1080p
- [ ] Métadonnées Kodi de base
- [ ] Synopsis enrichi en vidéo
- [ ] Menu contextuel `Informations Medici.tv`
- [ ] Fiche détaillée riche Medici.tv
- [ ] Cache local 24 h des métadonnées riches
- [ ] Fallback sur cache ancien si Medici est temporairement indisponible

## 4. Gestion des erreurs
- [ ] Identifiants absents
- [ ] Identifiants invalides
- [ ] Session expirée
- [ ] Échec de refresh
- [ ] Timeout / erreur réseau
- [ ] Contenu indisponible
- [ ] Aucun flux disponible
- [ ] Page de métadonnées indisponible
- [ ] Recherche sans résultat
- [ ] Messages utilisateur simples
- [ ] Détails techniques uniquement dans `kodi.log`

## 5. Langues
- [ ] `resource.language.en_gb/strings.po`
- [ ] `resource.language.fr_fr/strings.po`
- [ ] Chaînes visibles retirées autant que possible de `addon.py`
- [ ] Réglages traduits
- [ ] Navigation traduite
- [ ] Messages d’erreur traduits
- [ ] Fiche détaillée traduite

## 6. Assets
- [ ] `icon.png`
- [ ] Idéalement 512×512
- [ ] `fanart.jpg`
- [ ] Idéalement 1280×720
- [ ] Pas d’asset Medici officiel tant qu’on n’a pas clarifié leur autorisation
- [ ] Vérifier que les assets correspondent bien à Medici

## 7. Qualité du code
- [ ] `python -m py_compile addon.py`
- [ ] Pas d’import inutilisé
- [ ] Pas de debug temporaire
- [ ] Logs préfixés `[Medici]`
- [ ] Pas d’URL hardcodée inutilement dupliquée
- [ ] Exceptions utilisateur propres
- [ ] Code du cache token propre
- [ ] Code du cache metadata propre

## 8. Tests fonctionnels
- [ ] Ouverture de chaque catégorie
- [ ] Lecture d’un concert
- [ ] Lecture d’un opéra
- [ ] Lecture d’un ballet
- [ ] Lecture audio-only
- [ ] Lecture vidéo
- [ ] Test 1080p
- [ ] Test 720p
- [ ] Test 480p
- [ ] Test recherche
- [ ] Test pagination
- [ ] Test favoris
- [ ] Test fiche `Informations Medici.tv`
- [ ] Test token expiré / refresh
- [ ] Test après redémarrage de Kodi
- [ ] Test headless via Kore/SSH autant que possible

## 9. README
- [ ] Description claire
- [ ] Caractère non officiel
- [ ] Fonctionnalités principales
- [ ] Installation ZIP
- [ ] Configuration compte Medici
- [ ] Mode audio / vidéo
- [ ] Qualités vidéo
- [ ] Captures d’écran
- [ ] Limites connues
- [ ] Licence
- [ ] Lien vers Medici.tv
- [ ] Mention que l’utilisateur doit disposer d’un compte valide

## 10. Validation Kodi
- [ ] `kodi-addon-checker`
- [ ] 0 erreur
- [ ] Examiner chaque warning
- [ ] Vérifier la structure du ZIP
- [ ] Vérifier que le dossier racine du ZIP est `plugin.audio.medici`
- [ ] Aucun fichier parasite dans le ZIP
- [ ] Tester installation depuis ZIP propre
- [ ] Tester première connexion après installation propre

## 11. Git / release
- [ ] `git status` propre
- [ ] Version mise à jour dans `addon.xml`
- [ ] Commit final
- [ ] Push GitHub
- [ ] Tag de version
- [ ] ZIP de release construit depuis la racine
- [ ] `unzip -t`
- [ ] Release GitHub
- [ ] Éventuellement PR vers le dépôt officiel Kodi

## 12. Points volontairement repoussés
- [ ] Ajout/suppression des favoris depuis Kodi → **V2**
- [ ] Intégration plus poussée avec Kore → **V2 si utile**
- [ ] Éventuels assets officiels Medici → après retour de Medici
