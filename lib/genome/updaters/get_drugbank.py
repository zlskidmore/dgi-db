__author__ = 'Alex H Wagner'

import wget
import zipfile
import os
import xml.etree.ElementTree as ET
import csv
import re
from version_logger import Version
from urllib.request import urlopen
from bs4 import BeautifulSoup
from get_entrez import Entrez


class DrugBank():

    def __init__(self):
        self.online_version = None
        self.get_online_version()
        self.version = Version('DrugBank', version=self.online_version)
        self.logged_version = self.version.last_logged_version()
        self.interactions = self.drug_info = None

    def is_current(self):
        """Returns True if local versions of Entrez files are up-to-date."""
        return self.version.is_current()

    def get_online_version(self):
        print('Checking DrugBank Version...')
        html = urlopen('http://www.drugbank.ca/downloads')
        bsObj = BeautifulSoup(html.read(), "html.parser")
        r = re.compile(r'Version ([\d\.]+)')
        match = r.search(bsObj.h1.text)
        if match:
            self.online_version = match.group(1)
        else:
            raise ValueError('Error loading online version.')

    @staticmethod
    def download_files():
        print('Downloading DrugBank XML...')
        filename = wget.download("http://www.drugbank.ca/system/downloads/current/drugbank.xml.zip")

        print('\nExtracting DrugBank XML...')
        zfile = zipfile.ZipFile(filename)
        zfile.extract('drugbank.xml', 'data')
        os.remove(filename)
        e = Entrez()
        e.update()

    def parse(self):
        print('Parsing Entrez...')
        symbol_to_info = dict()
        hgnc_id_to_info = dict()
        entrez_to_info = dict()
        sources = set()
        with open('data/gene_info.human') as f:
            c = csv.reader(f, delimiter='\t')
            for i, line in enumerate(c):
                if i == 0:
                    continue
                if line[0] != '9606':
                    continue
                gene_symbol = line[2]
                entrez_id = line[1]
                symbol_to_info[gene_symbol] = {'Entrez': entrez_id,
                                               'Symbol': gene_symbol}
                if line[5] == '-':
                    continue
                synonyms = line[5].split('|')
                for synonym in synonyms:
                    (source, accession) = synonym.split(':', 1)
                    symbol_to_info[gene_symbol][source] = accession
                    sources.add(source)
                if 'HGNC' in symbol_to_info[gene_symbol]:
                    hgnc_id_to_info[symbol_to_info[gene_symbol]['HGNC']] = symbol_to_info[gene_symbol]
                entrez_to_info[entrez_id] = symbol_to_info[gene_symbol]

        uniprot_to_entrez = dict()
        r = re.compile(r'[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}')
        # regex from: http://www.uniprot.org/help/accession_numbers
        with open('data/gene2accession.human') as f:
            c = csv.reader(f, delimiter='\t')
            for i, line in enumerate(c):
                if i == 0:
                    continue
                if line[0] != '9606':
                    continue
                uniprot_id = line[5].split('.',1)[0]
                if not r.match(uniprot_id):
                    continue
                entrez_id = line[1]
                uniprot_to_entrez[uniprot_id] = entrez_id

        print('Parsing DrugBank XML...')
        ns = {'entry': 'http://www.drugbank.ca'}

        tree = ET.parse('data/drugbank.xml')
        drugbank = tree.getroot()
        drugs = drugbank.findall('entry:drug', ns)

        interactions = dict()
        drug_info = dict()
        uniprot_fail = uniprot_success = 0
        hgnc_fail = hgnc_success = 0
        no_info = info = no_ensembl = 0
        total = 0
        for drug in drugs:
            drug_id = drug.find('entry:drugbank-id', ns).text
            drug_name = drug.find('entry:name', ns).text

            synonyms = drug.find('entry:synonyms', ns)
            drug_synonyms = set()
            for synonym in synonyms:
                language = synonym.get('language')
                if language == '' or language == 'English':
                    drug_synonyms.add(synonym.text)
            drug_cas_number = drug.find('entry:cas-number',ns).text
            drug_brands = set()
            for product in drug.find('entry:products', ns):
                drug_brands.add(product.find('entry:name', ns).text)
            for int_brand in drug.find('entry:international-brands', ns):
                drug_brands.add(int_brand.find('entry:name', ns).text)
            drug_type = drug.get('type')
            drug_groups = set()
            for group in drug.find('entry:groups', ns):
                drug_groups.add(group.text)
            drug_categories = set()
            for category in drug.find('entry:categories', ns):
                drug_categories.add(category.find('entry:category', ns).text.lower())
            targets = drug.find('entry:targets', ns)
            if len(targets) == 0:
                continue
            drug_info[drug_id] = (drug_name, tuple(sorted(drug_synonyms)), drug_cas_number,
                                  tuple(sorted(drug_brands)), drug_type,
                                  tuple(sorted(drug_groups)), tuple(sorted(drug_categories)))
            for target in targets:
                organism = target.find('entry:organism', ns).text
                if organism != 'Human':
                    continue
                gene_id = target.find('entry:id',ns).text
                known_action = target.find('entry:known-action', ns).text
                target_actions = set()
                for action in target.find('entry:actions', ns):
                    target_actions.add(action.text)
                gene_symbol = hgnc_gene_acc = uniprot_id = entrez_id = ensembl_id = None
                raw_refs = target.find('entry:references', ns).text
                refs_regex = re.compile(r'"Pubmed":http://www.ncbi.nlm.nih.gov/pubmed/(\d+)')
                references = set()
                try:
                    for string in raw_refs.split('#'):
                        match = refs_regex.search(string)
                        if match:
                            references.add(match.group(1))
                except AttributeError:
                    pass
                references = tuple(references)
                polypeptide = target.find('entry:polypeptide', ns)
                synonyms = None
                if polypeptide is not None:
                    gene_symbol = polypeptide.find('entry:gene-name', ns).text
                    for identifier in polypeptide.find('entry:external-identifiers', ns):
                        if identifier.find('entry:resource',ns).text == 'HUGO Gene Nomenclature Committee (HGNC)':
                            hgnc_gene_acc = identifier.find('entry:identifier', ns).text
                            # Some identifiers are incorrectly labeled by DrugBank
                            r = re.compile(r'^\d+$')
                            if hgnc_gene_acc.startswith('GNC:'):
                                hgnc_gene_acc = 'H' + hgnc_gene_acc
                            elif r.match(hgnc_gene_acc):
                                hgnc_gene_acc = 'HGNC:' + hgnc_gene_acc
                            try:
                                synonyms = hgnc_id_to_info[hgnc_gene_acc]
                            except:
                                hgnc_fail += 1
                            else:
                                entrez_id = synonyms['Entrez']
                                try:
                                    ensembl_id = synonyms['Ensembl']
                                except KeyError:
                                    no_ensembl += 1
                                hgnc_success += 1
                        elif identifier.find('entry:resource',ns).text == 'UniProtKB':
                            uniprot_id = identifier.find('entry:identifier', ns).text
                            if not synonyms:
                                try:
                                    entrez_id = uniprot_to_entrez[uniprot_id]
                                    synonyms = entrez_to_info[entrez_id]
                                except KeyError:
                                    uniprot_fail += 1
                                else:
                                    uniprot_success += 1
                    if not synonyms:
                        try:
                            synonyms = symbol_to_info[gene_symbol]
                        except KeyError:
                            no_info += 1
                        else:
                            entrez_id = synonyms['Entrez']
                            ensembl_id = synonyms['Ensembl']
                            info += 1
                interaction_tuple = (gene_id, known_action, tuple(sorted(target_actions)),
                                     gene_symbol, uniprot_id, entrez_id, ensembl_id, references)
                total += 1
                try:
                    interactions[drug_id].append(interaction_tuple)
                except KeyError:
                    interactions[drug_id] = [interaction_tuple, ]
        self.interactions = interactions
        self.drug_info = drug_info

    def write(self):
        print('Writing to .tsv...')
        i = 0
        no_ensembl = no_entrez = total = 0
        header = ('count', 'drug_id', 'drug_name', 'drug_synonyms', 'drug_cas_number', 'drug_brands',
                  'drug_type', 'drug_groups', 'drug_categories', 'gene_id', 'known_action', 'target_actions',
                  'gene_symbol', 'uniprot_id', 'entrez_id', 'ensembl_id', 'pmid')
        with open('data/DrugBankInteractions.tsv', 'w') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(header)
            for drug in sorted(self.interactions):
                for interaction in self.interactions[drug]:
                    i += 1
                    data = (i, drug) + self.drug_info[drug] + interaction
                    out = list()
                    for datum in data:
                        if isinstance(datum, tuple):
                            datum = ','.join(datum)
                        datum = str(datum).replace("\t", '')
                        if not datum or datum == 'None':
                            datum = 'N/A'
                        out.append(datum)
                        # Some small number of rows contain tabs within text.
                    if out[14] == 'N/A':
                        no_entrez += 1
                    if out[15] == 'N/A':
                        no_ensembl += 1
                    writer.writerow(out)
        self.version.write_log()

    def update(self):
        if not self.is_current():
            self.download_files()
            self.parse()
            self.write()


if __name__ == '__main__':
    db = DrugBank()
    db.update()
    print('Done.')
