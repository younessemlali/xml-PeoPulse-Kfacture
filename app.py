import streamlit as st
import pandas as pd
from lxml import etree
import io
import zipfile
from datetime import datetime
import logging
from typing import Dict, List, Tuple, Optional
import re

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CMADProcessor:
    """Classe pour traiter les fichiers XML CMAD."""
    
    def __init__(self, xml_content: bytes):
        """
        Initialise le processeur avec le contenu XML.
        
        Args:
            xml_content: Contenu du fichier XML en bytes
        """
        self.parser = etree.XMLParser(encoding='iso-8859-1')
        self.tree = etree.fromstring(xml_content, self.parser)
        self.modifications = []
        
    def parse_decimal(self, value: str) -> float:
        """
        Parse une valeur décimale qui peut avoir une virgule ou un point.
        
        Args:
            value: Chaîne contenant le nombre
            
        Returns:
            float: Valeur numérique
        """
        if value:
            # Remplace la virgule par un point pour la conversion
            return float(value.replace(',', '.'))
        return 0.0
    
    def format_decimal(self, value: float, decimals: int = 4) -> str:
        """
        Formate un nombre avec le nombre de décimales spécifié et une virgule.
        
        Args:
            value: Valeur numérique
            decimals: Nombre de décimales
            
        Returns:
            str: Valeur formatée avec virgule comme séparateur
        """
        formatted = f"{value:.{decimals}f}"
        return formatted.replace('.', ',')
    
    def group_contdet_by_rucode(self, contrat: etree.Element) -> Dict[str, List[etree.Element]]:
        """
        Groupe les éléments CONTDET_X par leur RUCODE.
        
        Args:
            contrat: Élément CONTRAT
            
        Returns:
            Dict: Dictionnaire {rucode: [list of contdet elements]}
        """
        groups = {}
        
        # Recherche tous les éléments CONTDET_X
        for elem in contrat:
            if elem.tag.startswith('CONTDET_'):
                rucode_elem = elem.find('RUCODE')
                if rucode_elem is not None and rucode_elem.text:
                    rucode = rucode_elem.text
                    if rucode not in groups:
                        groups[rucode] = []
                    groups[rucode].append(elem)
        
        return groups
    
    def find_max_k_facture(self, contdet_list: List[etree.Element]) -> Tuple[float, str]:
        """
        Trouve le K_FACTURE maximum dans une liste de CONTDET.
        
        Args:
            contdet_list: Liste d'éléments CONTDET
            
        Returns:
            Tuple: (valeur max, valeur formatée)
        """
        max_k = 0.0
        max_k_str = "0"
        
        for contdet in contdet_list:
            k_elem = contdet.find('K_FACTURE')
            if k_elem is not None and k_elem.text:
                k_value = self.parse_decimal(k_elem.text)
                if k_value > max_k:
                    max_k = k_value
                    max_k_str = k_elem.text
        
        return max_k, max_k_str
    
    def update_contdet_group(self, contdet_list: List[etree.Element], new_k_facture: str) -> List[dict]:
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
            # Récupération des anciennes valeurs
            k_elem = contdet.find('K_FACTURE')
            taux_paye_elem = contdet.find('TAUX_PAYE')
            taux_facture_elem = contdet.find('TAUX_FACTURE')
            libelle_elem = contdet.find('LIBELLE')
            
            if k_elem is not None and taux_paye_elem is not None:
                old_k = k_elem.text
                old_taux_facture = taux_facture_elem.text if taux_facture_elem is not None else ""
                
                # Mise à jour du K_FACTURE
                k_elem.text = new_k_facture
                
                # Recalcul du TAUX_FACTURE
                taux_paye_value = self.parse_decimal(taux_paye_elem.text)
                new_taux_facture_value = taux_paye_value * new_k_value
                new_taux_facture_str = self.format_decimal(new_taux_facture_value)
                
                if taux_facture_elem is not None:
                    taux_facture_elem.text = new_taux_facture_str
                
                # Enregistrement de la modification
                modifications.append({
                    'contdet': contdet.tag,
                    'libelle': libelle_elem.text if libelle_elem is not None else "",
                    'old_k': old_k,
                    'new_k': new_k_facture,
                    'old_taux_facture': old_taux_facture,
                    'new_taux_facture': new_taux_facture_str,
                    'taux_paye': taux_paye_elem.text
                })
        
        return modifications
    
    def process_contrat(self, contrat: etree.Element) -> dict:
        """
        Traite un élément CONTRAT complet.
        
        Args:
            contrat: Élément CONTRAT
            
        Returns:
            dict: Résumé des modifications
        """
        contrat_id = ""
        # Récupération de l'identifiant du contrat
        for id_field in ['CONO', 'NUM_INTERNE', 'CONO_TXT']:
            elem = contrat.find(id_field)
            if elem is not None and elem.text:
                contrat_id = elem.text
                break
        
        modifications = {
            'contrat_id': contrat_id,
            'rucode_modifications': {}
        }
        
        # Grouper par RUCODE
        rucode_groups = self.group_contdet_by_rucode(contrat)
        
        # Traiter chaque groupe
        all_max_k_values = []
        
        for rucode, contdet_list in rucode_groups.items():
            max_k_value, max_k_str = self.find_max_k_facture(contdet_list)
            all_max_k_values.append(max_k_value)
            
            # Mettre à jour tous les CONTDET du groupe
            group_modifications = self.update_contdet_group(contdet_list, max_k_str)
            
            if group_modifications:
                modifications['rucode_modifications'][rucode] = {
                    'max_k': max_k_str,
                    'details': group_modifications
                }
        
        # Mettre à jour le K_FACTURE au niveau CONTRAT
        if all_max_k_values:
            global_max = max(all_max_k_values)
            k_contrat_elem = contrat.find('K_FACTURE')
            
            if k_contrat_elem is not None:
                old_k_contrat = k_contrat_elem.text
                k_contrat_value = self.parse_decimal(old_k_contrat)
                
                if global_max > k_contrat_value:
                    # Recherche de la valeur string correspondante
                    for rucode_data in modifications['rucode_modifications'].values():
                        if self.parse_decimal(rucode_data['max_k']) == global_max:
                            k_contrat_elem.text = rucode_data['max_k']
                            modifications['k_contrat_updated'] = {
                                'old': old_k_contrat,
                                'new': rucode_data['max_k']
                            }
                            break
        
        return modifications
    
    def process(self) -> Tuple[bytes, List[dict]]:
        """
        Traite le fichier XML complet.
        
        Returns:
            Tuple: (XML modifié en bytes, liste des modifications)
        """
        all_modifications = []
        
        # Traiter tous les contrats
        for contrat in self.tree.findall('.//CONTRAT'):
            modifications = self.process_contrat(contrat)
            if modifications['rucode_modifications'] or modifications.get('k_contrat_updated'):
                all_modifications.append(modifications)
        
        # Générer le XML modifié
        xml_output = etree.tostring(
            self.tree,
            pretty_print=True,
            encoding='iso-8859-1',
            xml_declaration=True
        )
        
        return xml_output, all_modifications


def create_modifications_dataframe(modifications: List[dict]) -> pd.DataFrame:
    """
    Crée un DataFrame pour afficher les modifications.
    
    Args:
        modifications: Liste des modifications
        
    Returns:
        pd.DataFrame: Tableau des modifications
    """
    rows = []
    
    for contrat_mod in modifications:
        contrat_id = contrat_mod['contrat_id']
        
        for rucode, rucode_data in contrat_mod['rucode_modifications'].items():
            # Compter les modifications réelles (où old_k != new_k)
            real_changes = [d for d in rucode_data['details'] if d['old_k'] != d['new_k']]
            
            if real_changes:
                # Récupérer les anciennes valeurs uniques
                old_k_values = list(set(d['old_k'] for d in real_changes))
                
                rows.append({
                    'Contrat': contrat_id,
                    'RUCODE': rucode,
                    'Ancien(s) K_FACTURE': ', '.join(old_k_values),
                    'Nouveau K_FACTURE': rucode_data['max_k'],
                    'Nb modifications': len(real_changes)
                })
    
    return pd.DataFrame(rows)


def main():
    """Fonction principale de l'application Streamlit."""
    st.set_page_config(
        page_title="Correcteur XML CMAD",
        page_icon="🔧",
        layout="wide"
    )
    
    st.title("🔧 Correcteur automatique de fichiers XML CMAD")
    st.markdown("""
    Cette application corrige automatiquement les coefficients K_FACTURE dans les fichiers XML CMAD de Peopulse.
    
    **Principe de fonctionnement :**
    - Pour chaque code rubrique (RUCODE), l'application trouve le K_FACTURE le plus élevé
    - Toutes les entrées du même RUCODE sont mises à jour avec ce coefficient maximum
    - Les TAUX_FACTURE sont recalculés automatiquement (TAUX_PAYE × K_FACTURE)
    """)
    
    # Upload de fichiers
    uploaded_files = st.file_uploader(
        "Choisissez un ou plusieurs fichiers XML",
        type=['xml'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.markdown("---")
        
        # Traitement des fichiers
        processed_files = []
        all_modifications = []
        
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
                modified_xml, modifications = processor.process()
                
                # Stockage des résultats
                processed_files.append({
                    'name': uploaded_file.name,
                    'content': modified_xml,
                    'modifications': modifications
                })
                
                all_modifications.extend(modifications)
                
            except Exception as e:
                st.error(f"❌ Erreur lors du traitement de {uploaded_file.name}: {str(e)}")
                logger.error(f"Erreur traitement {uploaded_file.name}", exc_info=True)
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        status_text.text("Traitement terminé!")
        
        # Affichage du résumé
        if all_modifications:
            st.markdown("## 📊 Résumé des modifications")
            
            # Statistiques
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Fichiers traités", len(processed_files))
            with col2:
                st.metric("Contrats modifiés", len(all_modifications))
            with col3:
                total_changes = sum(
                    len(mod['rucode_modifications']) 
                    for mod in all_modifications
                )
                st.metric("RUCODE modifiés", total_changes)
            
            # Tableau détaillé
            st.markdown("### Détail des modifications par RUCODE")
            df_modifications = create_modifications_dataframe(all_modifications)
            
            if not df_modifications.empty:
                st.dataframe(
                    df_modifications,
                    use_container_width=True,
                    hide_index=True
                )
            
            # Logs détaillés (expandable)
            with st.expander("📋 Voir les logs détaillés"):
                for mod in all_modifications:
                    st.write(f"**Contrat {mod['contrat_id']}**")
                    
                    for rucode, rucode_data in mod['rucode_modifications'].items():
                        st.write(f"- RUCODE {rucode}: K_FACTURE max = {rucode_data['max_k']}")
                        
                        for detail in rucode_data['details']:
                            if detail['old_k'] != detail['new_k']:
                                st.write(
                                    f"  - {detail['contdet']} ({detail['libelle']}): "
                                    f"K={detail['old_k']}→{detail['new_k']}, "
                                    f"TAUX_FACTURE={detail['old_taux_facture']}→{detail['new_taux_facture']}"
                                )
                    
                    if 'k_contrat_updated' in mod:
                        st.write(
                            f"- K_FACTURE du contrat: "
                            f"{mod['k_contrat_updated']['old']}→{mod['k_contrat_updated']['new']}"
                        )
                    
                    st.write("")
        
        # Téléchargement des fichiers
        st.markdown("## 💾 Télécharger les fichiers corrigés")
        
        if len(processed_files) == 1:
            # Un seul fichier : téléchargement direct
            file_data = processed_files[0]
            st.download_button(
                label=f"📥 Télécharger {file_data['name']}",
                data=file_data['content'],
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
                        file_data['content']
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


if __name__ == "__main__":
    main()
