# Correcteur XML CMAD Peopulse

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

Application web Streamlit pour corriger automatiquement les coefficients K_FACTURE dans les fichiers XML CMAD de Peopulse.

## 🎯 Fonctionnalités

- **Correction automatique** : Pour chaque code rubrique (RUCODE), sélection automatique du K_FACTURE le plus élevé
- **Recalcul des taux** : Mise à jour automatique des TAUX_FACTURE (TAUX_PAYE × K_FACTURE)
- **Traitement par lot** : Support de plusieurs fichiers XML simultanément
- **Rapport détaillé** : Tableau récapitulatif et logs des modifications
- **Téléchargement** : Export des fichiers corrigés individuellement ou en ZIP

## 📸 Capture d'écran

![Interface de l'application](screenshot.png)

## 🚀 Installation

### Prérequis

- Python 3.10 ou supérieur
- pip (gestionnaire de paquets Python)

### Étapes d'installation

1. Cloner le repository :
```bash
git clone https://github.com/votre-username/cmad-xml-corrector.git
cd cmad-xml-corrector
```

2. Créer un environnement virtuel (recommandé) :
```bash
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Lancer l'application :
```bash
streamlit run app.py
```

L'application s'ouvrira automatiquement dans votre navigateur à l'adresse `http://localhost:8501`

## 📖 Utilisation

1. **Charger les fichiers** : Cliquez sur "Browse files" et sélectionnez un ou plusieurs fichiers XML CMAD
2. **Traitement automatique** : L'application analyse et corrige automatiquement les coefficients
3. **Consulter le rapport** : Vérifiez les modifications dans le tableau récapitulatif
4. **Télécharger** : Récupérez les fichiers corrigés via les boutons de téléchargement

## 🔧 Logique métier

### Règles de traitement

Pour chaque contrat dans le fichier XML :

1. **Groupement par RUCODE** : Les balises `CONTDET_X` sont regroupées par leur code rubrique
2. **Sélection du maximum** : Pour chaque groupe, le K_FACTURE le plus élevé est identifié
3. **Mise à jour globale** : Toutes les entrées du groupe reçoivent ce K_FACTURE maximum
4. **Recalcul** : TAUX_FACTURE = TAUX_PAYE × K_FACTURE (arrondi à 4 décimales)
5. **Propagation** : Si nécessaire, le K_FACTURE au niveau CONTRAT est aussi mis à jour

### Exemple

Avant correction :
```xml
<CONTDET_1>
  <RUCODE>1100</RUCODE>
  <K_FACTURE>2,01</K_FACTURE>
</CONTDET_1>
<CONTDET_2>
  <RUCODE>1100</RUCODE>
  <K_FACTURE>1,95</K_FACTURE>
</CONTDET_2>
```

Après correction :
```xml
<CONTDET_1>
  <RUCODE>1100</RUCODE>
  <K_FACTURE>2,01</K_FACTURE>
</CONTDET_1>
<CONTDET_2>
  <RUCODE>1100</RUCODE>
  <K_FACTURE>2,01</K_FACTURE>
</CONTDET_2>
```

## 🧪 Tests

Pour exécuter les tests unitaires :

```bash
pytest tests/
```

## 🚀 Déploiement sur Streamlit Cloud

1. Push le code sur GitHub
2. Connectez-vous à [Streamlit Cloud](https://streamlit.io/cloud)
3. Créez une nouvelle app et liez-la à votre repository
4. L'application sera automatiquement déployée

## 📝 Structure du projet

```
cmad-xml-corrector/
├── app.py              # Application principale Streamlit
├── requirements.txt    # Dépendances Python
├── README.md          # Documentation
├── .gitignore         # Fichiers à ignorer
└── tests/             # Tests unitaires
    └── test_logic.py
```

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

1. Fork le projet
2. Créer une branche (`git checkout -b feature/amelioration`)
3. Commit vos changements (`git commit -am 'Ajout de fonctionnalité'`)
4. Push la branche (`git push origin feature/amelioration`)
5. Créer une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 👤 Auteur

Votre Nom - [@votre-twitter](https://twitter.com/votre-twitter)

## 🙏 Remerciements

- Peopulse pour le format XML CMAD
- Streamlit pour le framework web
- lxml pour le parsing XML performant
