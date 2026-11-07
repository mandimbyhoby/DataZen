# DataClean Pro — workflow n8n

`datacleanpro-workflow.json` est le workflow n8n « DataClean Pro » corrigé pour
traiter **plusieurs formats de fichiers** en entrée.

## Formats pris en charge

| Format | Opération « Extract from File » | Délimiteur |
| ------ | ------------------------------- | ---------- |
| CSV    | `csv`                           | `,`        |
| TSV    | `csv`                           | tabulation |
| TXT    | `text`                          | détecté    |
| JSON   | `fromJson`                      | —          |
| XLSX   | `xlsx`                          | —          |
| XLS    | `xls`                           | —          |
| ODS    | `ods`                           | —          |

## Détection du format

Le nœud **Identifier le service et le prix** calcule le format une seule fois et
l'expose aux nœuds suivants :

- `fileFormat` — format retenu (`csv`, `tsv`, `txt`, `json`, `xlsx`, `xls`, `ods`)
- `fileFormatSource` — origine : `champ Tally`, `extension URL` ou `valeur par défaut`
- `fileFormatWarning` — message si le format déclaré contredit l'extension du fichier
- `fileUrl` — URL du fichier téléversé
- `originalFileName` / `baseName` — nom d'origine et nom sans extension
- `extractOperation` / `extractDelimiter` — paramètres consommés par « Extract from File »

Deux sources sont combinées :

1. **Champ Tally** — la question « format du fichier » du formulaire.
2. **Extension de l'URL** — déduite du fichier réellement téléversé.

En cas de désaccord, **l'extension du fichier gagne** (le fichier physique ne
ment pas) et un avertissement est écrit dans `fileFormatWarning`.

### Configurer le champ Tally

Dans le nœud **Identifier le service et le prix**, en tête du script :

```js
const FORMAT_FIELD_ID = ''; // ex. 'question_AbC123'
```

- **Vide** → détection automatique : le script balaie les champs `question_*`
  (hors service, e-mail, nom et instructions) et retient la première valeur
  reconnue comme un format.
- **Renseigné** → ce champ est utilisé en priorité.

## Nœuds modifiés

| Nœud | Changement |
| ---- | ---------- |
| `Identifier le service et le prix` | Détection et normalisation du format + du nom de fichier |
| `HTTP Request` | URL lue depuis `fileUrl` au lieu de `$json.question_ZGkd5z.value` |
| `Extract from File` | `operation` et `delimiter` dynamiques (au lieu de CSV figé) |
| `Normaliser les lignes extraites` | **Nouveau** — un item = une ligne, quel que soit le format |
| `Code in JavaScript` | Nom de fichier et format lus depuis le nœud d'identification |
| `Convert to File`, `Convert to File1`, `Convert to File2`, `Convert to File — À vérifier` | Noms de fichiers dérivés de `baseName` |
| `Read/Write Files from Disk` (×4) | Noms de fichiers dérivés de `baseName` |
| `Edit Fields` | `originalFileName` lu depuis le nœud d'identification |

## Fichiers produits

Pour un fichier source `ventes mars.xlsx` :

- `/output/ventes mars_nettoye.csv`
- `/output/ventes mars_rapport_qualite.csv`
- `/output/ventes mars_interface.html`
- `/output/ventes mars_a_verifier.csv` (service B, lignes non conformes)

## Importer le workflow

1. n8n → **Workflows** → **Import from File**
2. Sélectionner `datacleanpro-workflow.json`
3. Reconfigurer les identifiants : `tallyApi` (Tally Trigger) et SMTP (Send an Email1)
4. Renseigner les adresses d'expédition et de réception des nœuds **Send an Email**
   (elles sont livrées avec les valeurs neutres `noreply@example.com` / `client@example.com`)
5. Vérifier que le dossier `/output/` existe et est accessible en écriture
   (en mode cloud n8n, les chemins doivent être sous `/home/node/`)

## Données sensibles

Le fichier ne contient **aucun secret** : les identifiants n8n sont référencés par
identifiant (`tallyApi`, `smtp`) et doivent être recréés à l'import. Les adresses
e-mail personnelles et l'`instanceId` de l'instance d'origine ont été retirés.
