import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom
import defusedxml.ElementTree as defusedET
import io
import zipfile
from datetime import datetime
import logging
from typing import Dict, List, Tuple, Optional, Union
import re
import traceback

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CMADProcessor:
    """Classe pour traiter les fichiers XML CMAD de manière robuste."""
    
    def __init__(self, xml_content: Union[str, bytes]):
        """
        Initialise le processeur avec le contenu XML.
        
        Args:
            xml_content: Contenu du fichier XML en str ou bytes
        """
        self.xml_content = xml_content
        self.tree = None
        self.root = None
        self.encoding = 'iso-8859-1'
        self.modifications = []
        self.errors = []
        
        # Parse le XML de manière sécurisée
        self._parse_xml()
    
    def _parse_xml(self):
        """Parse le XML de manière sécurisée avec gestion d'erreurs."""
        try:
            # Convertir en string si nécessaire
            if isinstance(self.xml_content, bytes):
                # Détecter l'encodage si possible
                try:
                    self.xml_content = self.xml_content.decode('iso-8859-1')
                except UnicodeDecodeError:
                    try:
                        self.xml_content = self.xml_content.decode('utf-8')
                        self.encoding = 'utf-8'
                    except UnicodeDecodeError:
                        self.xml_content = self.xml_content.decode('latin-1')
                        self.encoding = 'latin-1'
            
            # Utiliser defusedxml pour la sécurité
            self.root = defusedET.fromstring(self.xml_content)
            self.tree = None  # On n'utilise pas ElementTree avec defusedxml
            
        except ET.ParseError as e:
            # Essayer de réparer le XML si possible
            self._try_repair_xml()
            if not self.root:
                raise ValueError(f"Impossible de parser le XML: {str(e)}")
        except Exception as e:
            raise ValueError(f"Erreur lors du parsing XML: {str(e)}")
    
    def _try_repair_xml(self):
        """Tente de réparer un XML mal formé."""
        try:
            # Essayer de nettoyer le XML
            cleaned_xml = self.xml_content
            
            # Remplacer les caractères problématiques courants
            replacements = [
                ('&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;'),  # & non échappés
                ('<(?=\s)', '&lt;'),  # < suivis d'espaces
                ('(?<!\s)>', '&gt;'),  # > non précédés d'espaces
            ]
            
            for pattern, replacement in replacements:
                cleaned_xml = re.sub(pattern, replacement, cleaned_xml)
            
            # Réessayer le parsing
            self.root = defusedET.fromstring(cleaned_xml)
            self.tree = None
            self.errors.append("XML réparé avec succès (caractères non échappés corrigés)")
            
        except Exception as e:
            logger.error(f"Impossible de réparer le XML: {str(e)}")
    
    def parse_decimal(self, value: Optional[str]) -> float:
        """
        Parse une valeur décimale de manière robuste.
        
        Args:
            value: Chaîne contenant le nombre (peut être None)
            
        Returns:
            float: Valeur numérique
        """
        if not value:
            return 0.0
        
        try:
            # Nettoyer la valeur
            value = value.strip()
            
            # Gérer différents formats de nombres
            # Remplacer la virgule par un point
            value = value.replace(',', '.')
            
            # Gérer les espaces comme séparateurs de milliers
            value = value.replace(' ', '')
            
            # Gérer le format avec point comme séparateur de milliers
            if value.count('.') > 1:
                # Ex: "1.234.567,89" -> "1234567.89"
                parts = value.split('.')
                value = ''.join(parts[:-1]) + '.' + parts[-1]
            
            return float(value)
            
        except (ValueError, AttributeError) as e:
            logger.warning(f"Impossible de parser la valeur décimale '{value}': {str(e)}")
            return 0.0
    
    def format_decimal(self, value: float, decimals: int = 4) -> str:
        """
        Formate un nombre avec le nombre de décimales spécifié.
        
        Args:
            value: Valeur numérique
            decimals: Nombre de décimales
            
        Returns:
            str: Valeur formatée avec virgule comme séparateur
        """
        try:
            # Formater avec le bon nombre de décimales
            formatted = f"{value:.{decimals}f}"
            
            # Remplacer le point par une virgule
            formatted = formatted.replace('.', ',')
            
            return formatted
            
        except Exception as e:
            logger.warning(f"Erreur lors du formatage de {value}: {str(e)}")
            return str(value).replace('.', ',')
    
    def find_elements_by_pattern(self, parent: ET.Element, pattern: str) -> List[ET.Element]:
        """
        Trouve des éléments par pattern (supporte CONTDET_X).
        
        Args:
            parent: Élément parent
            pattern: Pattern à rechercher (ex: "CONTDET_")
            
        Returns:
            List: Liste des éléments trouvés
        """
        elements = []
        
        try:
            for elem in parent:
                if elem.tag and elem.tag.startswith(pattern):
                    elements.append(elem)
        except Exception as e:
            logger.error(f"Erreur lors de la recherche d'éléments: {str(e)}")
        
        return elements
    
    def get_element_text(self, element: ET.Element, tag: str, default: str = "") -> str:
        """
        Récupère le texte d'un sous-élément de manière sûre.
        
        Args:
            element: Élément parent
            tag: Tag du sous-élément
            default: Valeur par défaut
            
        Returns:
            str: Texte de l'élément ou valeur par défaut
        """
        try:
            sub_elem = element.find(tag)
            if sub_elem is not None and sub_elem.text:
                return sub_elem.text.strip()
        except Exception as e:
            logger.warning(f"Erreur lors de la récupération de {tag}: {str(e)}")
        
        return default
    
    def set_element_text(self, element: ET.Element, tag: str, value: str) -> bool:
        """
        Définit le texte d'un sous-élément de manière sûre.
        
        Args:
            element: Élément parent
            tag: Tag du sous-élément
            value: Nouvelle valeur
            
        Returns:
            bool: True si succès, False sinon
        """
        try:
            sub_elem = element.find(tag)
            if sub_elem is not None:
                sub_elem.text = value
                return True
        except Exception as e:
            logger.warning(f"Erreur lors de la mise à jour de {tag}: {str(e)}")
        
        return False
    
    def group_contdet_by_rucode(self, contrat: ET.Element) -> Dict[str, List[ET.Element]]:
        """
        Groupe les éléments CONTDET_X par leur RUCODE.
        
        Args:
            contrat: Élément CONTRAT
            
        Returns:
            Dict: Dictionnaire {rucode: [list of contdet elements]}
        """
        groups = {}
        
        try:
            # Rechercher tous les éléments CONTDET_X
            contdet_elements = self.find_elements_by_pattern(contrat, 'CONTDET_')
            
            for contdet in contdet_elements:
                rucode = self.get_element_text(contdet, 'RUCODE')
                
                if rucode:
                    if rucode not in groups:
                        groups[rucode] = []
                    groups[rucode].append(contdet)
                else:
                    logger.warning(f"CONTDET sans RUCODE trouvé: {contdet.tag}")
        
        except Exception as e:
            logger.error(f"Erreur lors du groupement par RUCODE: {str(e)}")
        
        return groups
    
    def find_max_k_facture(self, contdet_list: List[ET.Element]) -> Tuple[float, str]:
        """
        Trouve le K_FACTURE maximum dans une liste de CONTDET.
        
        Args:
            contdet_list: Liste d'éléments CONTDET
            
        Returns:
            Tuple: (valeur max, valeur formatée originale)
        """
        max_k = 0.0
        max_k_str = "0"
        
        try:
            for contdet in contdet_list:
                k_facture_text = self.get_element_text(contdet, 'K_FACTURE')
                
                if k_facture_text:
                    k_value = self.parse_decimal(k_facture_text)
                    
                    if k_value > max_k:
                        max_k = k_value
                        max_k_str = k_facture_text
        
        except Exception as e:
            logger.error(f"Erreur lors de la recherche du K_FACTURE max: {str(e)}")
        
        return max_k, max_k_str
    
    def update_contdet_group(self, contdet_list: List[ET.Element], new_k_facture: str) -> List[dict]:
        """
        Met à jour tous les CONTDET d'un groupe avec le nouveau K_FACTURE.
        
        Args:
            contdet_list: Liste d'éléments CONTDET
            new_k_facture: Nouvelle valeur de K_FACTURE (string)
            
        Returns:
            List: Liste des modifications effectuées
        """
        modifications = []
        new_k_value = self.parse_decimal(new_k_facture)
        
        for contdet in contdet_list:
            try:
                # Récupération des valeurs actuelles
                old_k = self.get_element_text(contdet, 'K_FACTURE')
                taux_paye_text = self.get_element_text(contdet, 'TAUX_PAYE')
                old_taux_facture = self.get_element_text(contdet, 'TAUX_FACTURE')
                libelle = self.get_element_text(contdet, 'LIBELLE', contdet.tag)
                
                if old_k and taux_paye_text:
                    # Mise à jour du K_FACTURE
                    if self.set_element_text(contdet, 'K_FACTURE', new_k_facture):
                        
                        # Recalcul du TAUX_FACTURE
                        taux_paye_value = self.parse_decimal(taux_paye_text)
                        new_taux_facture_value = taux_paye_value * new_k_value
                        new_taux_facture_str = self.format_decimal(new_taux_facture_value)
                        
                        # Mise à jour du TAUX_FACTURE
                        self.set_element_text(contdet, 'TAUX_FACTURE', new_taux_facture_str)
                        
                        # Enregistrement de la modification
                        modifications.append({
                            'contdet': contdet.tag,
                            'libelle': libelle,
                            'old_k': old_k,
                            'new_k': new_k_facture,
                            'old_taux_facture': old_taux_facture,
                            'new_taux_facture': new_taux_facture_str,
                            'taux_paye': taux_paye_text
                        })
                    
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de {contdet.tag}: {str(e)}")
                self.errors.append(f"Erreur sur {contdet.tag}: {str(e)}")
        
        return modifications
    
    def process_contrat(self, contrat: ET.Element) -> dict:
        """
        Traite un élément CONTRAT complet.
        
        Args:
            contrat: Élément CONTRAT
            
        Returns:
            dict: Résumé des modifications
        """
        # Récupération de l'identifiant du contrat
        contrat_id = ""
        for id_field in ['CONO', 'NUM_INTERNE', 'CONO_TXT', 'NUMCLIENT']:
            contrat_id = self.get_element_text(contrat, id_field)
            if contrat_id:
                break
        
        if not contrat_id:
            contrat_id = "CONTRAT_SANS_ID"
        
        modifications = {
            'contrat_id': contrat_id,
            'rucode_modifications': {}
        }
        
        try:
            # Grouper par RUCODE
            rucode_groups = self.group_contdet_by_rucode(contrat)
            
            if not rucode_groups:
                logger.info(f"Aucun CONTDET trouvé dans le contrat {contrat_id}")
                return modifications
            
            # Traiter chaque groupe
            all_max_k_values = []
            
            for rucode, contdet_list in rucode_groups.items():
                if len(contdet_list) > 1:  # Ne traiter que s'il y a plusieurs CONTDET
                    max_k_value, max_k_str = self.find_max_k_facture(contdet_list)
                    
                    if max_k_value > 0:
                        all_max_k_values.append(max_k_value)
                        
                        # Mettre à jour tous les CONTDET du groupe
                        group_modifications = self.update_contdet_group(contdet_list, max_k_str)
                        
                        # Enregistrer seulement s'il y a eu des changements réels
                        real_changes = [m for m in group_modifications if m['old_k'] != m['new_k']]
                        
                        if real_changes:
                            modifications['rucode_modifications'][rucode] = {
                                'max_k': max_k_str,
                                'details': group_modifications
                            }
            
            # Mettre à jour le K_FACTURE au niveau CONTRAT si nécessaire
            if all_max_k_values:
                global_max = max(all_max_k_values)
                k_contrat_text = self.get_element_text(contrat, 'K_FACTURE')
                
                if k_contrat_text:
                    k_contrat_value = self.parse_decimal(k_contrat_text)
                    
                    if global_max > k_contrat_value:
                        # Trouver la valeur string correspondante
                        for rucode_data in modifications['rucode_modifications'].values():
                            if self.parse_decimal(rucode_data['max_k']) == global_max:
                                if self.set_element_text(contrat, 'K_FACTURE', rucode_data['max_k']):
                                    modifications['k_contrat_updated'] = {
                                        'old': k_contrat_text,
                                        'new': rucode_data['max_k']
                                    }
                                break
        
        except Exception as e:
            logger.error(f"Erreur lors du traitement du contrat {contrat_id}: {str(e)}")
            self.errors.append(f"Erreur contrat {contrat_id}: {str(e)}")
        
        return modifications
    
    def prettify_xml(self, element: ET.Element) -> str:
        """
        Formate le XML avec une indentation propre.
        
        Args:
            element: Élément racine
            
        Returns:
            str: XML formaté
        """
        try:
            # Convertir en string
            rough_string = ET.tostring(element, encoding='unicode')
            
            # Utiliser minidom pour formatter
            reparsed = minidom.parseString(rough_string)
            
            # Récupérer le XML formaté sans l'encoding (on va l'ajouter manuellement)
            pretty_xml = reparsed.documentElement.toprettyxml(indent="  ")
            
            # Nettoyer les lignes vides en trop
            lines = pretty_xml.split('\n')
            lines = [line.rstrip() for line in lines if line.strip()]
            
            # Reconstruire avec la déclaration XML
            result = '<?xml version="1.0" encoding="' + self.encoding + '"?>\n'
            result += '\n'.join(lines)
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors du formatage XML: {str(e)}")
            # Fallback: retourner le XML non formaté
            declaration = '<?xml version="1.0" encoding="' + self.encoding + '"?>\n'
            return declaration + ET.tostring(element, encoding='unicode')
    
    def process(self) -> Tuple[str, List[dict], List[str]]:
        """
        Traite le fichier XML complet.
        
        Returns:
            Tuple: (XML modifié en string, liste des modifications, liste des erreurs)
        """
        all_modifications = []
        
        if not self.root:
            return self.xml_content, [], ["Impossible de parser le XML"]
        
        try:
            # Traiter tous les contrats
            contrats = self.root.findall('.//CONTRAT')
            
            if not contrats:
                logger.warning("Aucun élément CONTRAT trouvé dans le XML")
                self.errors.append("Aucun élément CONTRAT trouvé")
            
            for contrat in contrats:
                modifications = self.process_contrat(contrat)
                
                if (modifications.get('rucode_modifications') or 
                    modifications.get('k_contrat_updated')):
                    all_modifications.append(modifications)
            
            # Générer le XML modifié
            xml_output = self.prettify_xml(self.root)
            
            return xml_output, all_modifications, self.errors
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement: {str(e)}")
            self.errors.append(f"Erreur générale: {str(e)}")
            return self.xml_content, [], self.errors


def create_modifications_dataframe(modifications: List[dict]) -> pd.DataFrame:
    """
    Crée un DataFrame pour afficher les modifications.
    
    Args:
        modifications: Liste des modifications
        
    Returns:
        pd.DataFrame: Tableau des modifications
    """
    rows = []
    
    try:
        for contrat_mod in modifications:
            contrat_id = contrat_mod.get('contrat_id', 'INCONNU')
            
            for rucode, rucode_data in contrat_mod.get('rucode_modifications', {}).items():
                # Compter les modifications réelles
                details = rucode_data.get('details', [])
                real_changes = [d for d in details if d.get('old_k') != d.get('new_k')]
                
                if real_changes:
                    # Récupérer les anciennes valeurs uniques
                    old_k_values = list(set(d.get('old_k', '?') for d in real_changes))
                    
                    rows.append({
                        'Contrat': contrat_id,
                        'RUCODE': rucode,
                        'Ancien(s) K_FACTURE': ', '.join(old_k_values),
                        'Nouveau K_FACTURE': rucode_data.get('max_k', '?'),
                        'Nb modifications': len(real_changes)
                    })
    
    except Exception as e:
        logger.error(f"Erreur lors de la création du DataFrame: {str(e)}")
    
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def main():
    """Fonction principale de l'application Streamlit."""
    # Configuration de la page
    try:
        st.set_page_config(
            page_title="Correcteur XML CMAD",
            page_icon="🔧",
            layout="wide"
        )
    except Exception:
        # En cas d'erreur (page déjà configurée), continuer
        pass
    
    st.title("🔧 Correcteur automatique de fichiers XML CMAD")
    st.markdown("""
    Cette application corrige automatiquement les coefficients K_FACTURE dans les fichiers XML CMAD de Peopulse.
    
    **Principe de fonctionnement :**
    - Pour chaque code rubrique (RUCODE), l'application trouve le K_FACTURE le plus élevé
    - Toutes les entrées du même RUCODE sont mises à jour avec ce coefficient maximum
    - Les TAUX_FACTURE sont recalculés automatiquement (TAUX_PAYE × K_FACTURE)
    
    **Robustesse :**
    - Support de différents encodages (ISO-8859-1, UTF-8, Latin-1)
    - Gestion des erreurs de parsing XML
    - Formats de nombres flexibles (virgule ou point comme séparateur)
    """)
    
    # Upload de fichiers
    uploaded_files = st.file_uploader(
        "Choisissez un ou plusieurs fichiers XML",
        type=['xml'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.markdown("---")
        
        # Options de traitement
        with st.expander("⚙️ Options avancées"):
            col1, col2 = st.columns(2)
            with col1:
                show_detailed_logs = st.checkbox("Afficher les logs détaillés", value=True)
            with col2:
                stop_on_error = st.checkbox("Arrêter en cas d'erreur", value=False)
        
        # Traitement des fichiers
        processed_files = []
        all_modifications = []
        all_errors = []
        
        # Barre de progression
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Traitement de {uploaded_file.name}...")
            
            try:
                # Lecture du fichier
                xml_content = uploaded_file.read()
                
                # Traitement
                processor = CMADProcessor(xml_content)
                modified_xml, modifications, errors = processor.process()
                
                # Stockage des résultats
                processed_files.append({
                    'name': uploaded_file.name,
                    'content': modified_xml,
                    'modifications': modifications,
                    'errors': errors
                })
                
                all_modifications.extend(modifications)
                all_errors.extend(errors)
                
                # Afficher les erreurs si présentes
                if errors and show_detailed_logs:
                    st.warning(f"⚠️ Avertissements pour {uploaded_file.name}:")
                    for error in errors:
                        st.write(f"- {error}")
                
            except Exception as e:
                error_msg = f"❌ Erreur lors du traitement de {uploaded_file.name}: {str(e)}"
                st.error(error_msg)
                logger.error(f"Erreur traitement {uploaded_file.name}", exc_info=True)
                
                if show_detailed_logs:
                    st.text("Détails de l'erreur:")
                    st.text(traceback.format_exc())
                
                if stop_on_error:
                    st.stop()
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        status_text.text("Traitement terminé!")
        
        # Affichage du résumé
        if all_modifications or processed_files:
            st.markdown("## 📊 Résumé des modifications")
            
            # Statistiques
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Fichiers traités", len(processed_files))
            with col2:
                st.metric("Contrats modifiés", len(all_modifications))
            with col3:
                total_changes = sum(
                    len(mod.get('rucode_modifications', {})) 
                    for mod in all_modifications
                )
                st.metric("RUCODE modifiés", total_changes)
            with col4:
                st.metric("Avertissements", len(all_errors), 
                         delta=None if len(all_errors) == 0 else f"{len(all_errors)} ⚠️")
            
            # Tableau détaillé
            if all_modifications:
                st.markdown("### Détail des modifications par RUCODE")
                df_modifications = create_modifications_dataframe(all_modifications)
                
                if not df_modifications.empty:
                    st.dataframe(
                        df_modifications,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Export CSV du rapport
                    csv = df_modifications.to_csv(index=False)
                    st.download_button(
                        label="📄 Télécharger le rapport CSV",
                        data=csv,
                        file_name=f"rapport_modifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            
            # Logs détaillés
            if show_detailed_logs and all_modifications:
                with st.expander("📋 Voir les logs détaillés"):
                    for mod in all_modifications:
                        st.write(f"**Contrat {mod.get('contrat_id', 'INCONNU')}**")
                        
                        for rucode, rucode_data in mod.get('rucode_modifications', {}).items():
                            st.write(f"- RUCODE {rucode}: K_FACTURE max = {rucode_data.get('max_k', '?')}")
                            
                            for detail in rucode_data.get('details', []):
                                if detail.get('old_k') != detail.get('new_k'):
                                    st.write(
                                        f"  - {detail.get('contdet', '?')} ({detail.get('libelle', '?')}): "
                                        f"K={detail.get('old_k', '?')}→{detail.get('new_k', '?')}, "
                                        f"TAUX_FACTURE={detail.get('old_taux_facture', '?')}→{detail.get('new_taux_facture', '?')}"
                                    )
                        
                        if 'k_contrat_updated' in mod:
                            update = mod['k_contrat_updated']
                            st.write(
                                f"- K_FACTURE du contrat: "
                                f"{update.get('old', '?')}→{update.get('new', '?')}"
                            )
                        
                        st.write("")
        
        # Téléchargement des fichiers
        if processed_files:
            st.markdown("## 💾 Télécharger les fichiers corrigés")
            
            if len(processed_files) == 1:
                # Un seul fichier : téléchargement direct
                file_data = processed_files[0]
                st.download_button(
                    label=f"📥 Télécharger {file_data['name']}",
                    data=file_data['content'].encode('utf-8'),
                    file_name=f"corrected_{file_data['name']}",
                    mime="application/xml"
                )
            else:
                # Plusieurs fichiers : créer un ZIP
                zip_buffer = io.BytesIO()
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for file_data in processed_files:
                        zip_file.writestr(
                            f"corrected_{file_data['name']}",
                            file_data['content'].encode('utf-8')
                        )
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label=f"📥 Télécharger tous les fichiers ({len(processed_files)} fichiers)",
                    data=zip_buffer,
                    file_name=f"corrected_xml_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip"
                )
        
    else:
        # Instructions si aucun fichier
        st.info("👆 Veuillez sélectionner un ou plusieurs fichiers XML à traiter")
        
        with st.expander("ℹ️ Format XML attendu"):
            st.code("""
<CMAD>
  <CONTRAT>
    <K_FACTURE>2,01</K_FACTURE>
    <CONTDET_1>
      <RUCODE>1100</RUCODE>
      <TAUX_PAYE>12,25000</TAUX_PAYE>
      <K_FACTURE>2,01</K_FACTURE>
      <TAUX_FACTURE>24,6225</TAUX_FACTURE>
    </CONTDET_1>
    <CONTDET_2>
      <RUCODE>1100</RUCODE>
      <TAUX_PAYE>12,25000</TAUX_PAYE>
      <K_FACTURE>1,95</K_FACTURE>
      <TAUX_FACTURE>23,8875</TAUX_FACTURE>
    </CONTDET_2>
    ...
  </CONTRAT>
</CMAD>
            """, language="xml")
        
        with st.expander("🛡️ Fonctionnalités de robustesse"):
            st.markdown("""
            - **Encodages supportés** : ISO-8859-1, UTF-8, Latin-1 (détection automatique)
            - **Formats de nombres** : Virgule ou point comme séparateur décimal
            - **Gestion d'erreurs** : Continue le traitement même si un fichier échoue
            - **XML mal formé** : Tentative de réparation automatique
            - **Logs détaillés** : Traçabilité complète des modifications
            - **Export CSV** : Rapport des modifications en format tabulaire
            """)


if __name__ == "__main__":
    main()
