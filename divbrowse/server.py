__version__ = '0.1.0'

import json
from timeit import default_timer as timer

from flask import Flask, Response, jsonify, request

import allel
import numpy as np
import pandas as pd
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.tools.inputs import inputs
from sklearn.metrics import pairwise_distances
import yaml

from divbrowse import log
from divbrowse.lib.annotation_data import AnnotationData
from divbrowse.lib.genotype_data import GenotypeData
from divbrowse.lib.analysis import Analysis


from divbrowse.lib.utils import ApiError
from divbrowse.lib.utils import StrictEncoder

# %% Import Libraries for phylogenitic 
from divbrowse.lib.utils import to_newick
from scipy.cluster.hierarchy import ClusterWarning, linkage, to_tree
from scipy.spatial import distance_matrix

def create_app(filename_config_yaml = 'divbrowse.config.yml', config_runtime=None):
    """Factory method to create and return a wsgi-compliant Flask app instance"""

    app = Flask(__name__, static_url_path='', static_folder='static')

    app.json_encoder = StrictEncoder

    if config_runtime is not None:
        log.info('Using runtime config')
        config = config_runtime
    else:

        try:
            with open(filename_config_yaml) as config_file:
                config = yaml.full_load(config_file)
        except FileNotFoundError:
            log.error('Divbrowse config file `divbrowse.config.yml` not found in current directory!')
            exit(1)


    log.info('Instanciate GenotypeData classes')
    gd = GenotypeData(config)

    log.info('Instanciate AnnotationData classes')
    ad = AnnotationData(config, gd)


    def process_request_vars(vars):

        processed = {
            'chrom': vars['chrom'],
        }

        try:

            if 'samples' in vars:
                # conversion to Python list from stringified JSON is necessary for form-data POST requests of vcf_export
                if type(vars['samples']) is str:
                    vars['samples'] = json.loads(vars['samples'])

                samples, unmapable_sample_ids = gd.map_input_sample_ids_to_vcf_sample_ids(vars['samples'])

                if len(unmapable_sample_ids) > 0:
                    raise ApiError('The following sample-IDs could not be resolved: '+', '.join(unmapable_sample_ids))

                processed['samples'] = samples

            processed['count'] = None
            if 'count' in vars:
                processed['count'] = int(vars['count'])

            processed['startpos'] = None
            if 'startpos' in vars:
                processed['startpos'] = int(vars['startpos'])

            processed['endpos'] = None
            if 'endpos' in vars:
                processed['endpos'] = int(vars['endpos'])

            processed['variant_filter_settings'] = None
            if 'variant_filter_settings' in vars:
                # conversion to Python list from stringified JSON is necessary for form-data POST requests of vcf_export
                if type(vars['variant_filter_settings']) is str:
                    vars['variant_filter_settings'] = json.loads(vars['variant_filter_settings'])
                processed['variant_filter_settings'] = vars['variant_filter_settings']

            return processed

        except KeyError:
            raise ApiError('Some input data is missing.')




    @app.route("/genomic_window_summary", methods = ['GET', 'POST', 'OPTIONS'])
    def __genomic_window_summary():

        if request.method == 'POST':
            input = process_request_vars(request.get_json(silent=True))
        else:
            return 'ERROR'

        variant_calls_slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        )

        result = variant_calls_slice.get_stats_dict()

        return jsonify(result)



    @app.route("/pca", methods = ['GET', 'POST', 'OPTIONS'])
    def __pca():

        payload = request.get_json(silent=True)

        if request.method == 'POST':
            input = process_request_vars(payload)
        else:
            return 'ERROR'

        umap_n_neighbors = int(payload['umap_n_neighbors'])

        variant_calls_slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        )

        analysis = Analysis(variant_calls_slice)

        pca_result, pca_explained_variance = analysis.pca()

        umap_result = analysis.umap(n_neighbors = umap_n_neighbors)

        result = {
            'pca_result': pca_result.tolist(),
            'pca_explained_variance': pca_explained_variance.tolist(),
            'umap_result': umap_result.tolist(),
        }

        return jsonify(result)


    @app.route("/phylo_cluster", methods = ['GET', 'POST', 'OPTIONS'])
    def __phylo_cluster():
        
        payload = request.get_json(silent=True)
        if request.method == 'POST':
            input = process_request_vars(payload)
        else:
            return 'ERROR'

        number_of_sample = payload['number_of_sample']


        _result = gd.get_slice_of_variant_calls( 
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        ) 

        df = pd.DataFrame(_result.numbers_of_alternate_alleles, index= _result.samples_selected_mapped)
        df = df.replace(-1, 0)
 
        sampel_data =pd.DataFrame(distance_matrix(df.values, df.values), index=df.index, columns=df.index)
        sampel_data = sampel_data.iloc[ : number_of_sample , : number_of_sample ]
        
        labelList = _result.samples_selected_mapped[:number_of_sample]
        Z1 = linkage(sampel_data, method='single', metric='euclidean')
        
        T = to_tree(Z1, rd=False)
        

        result = {
            'phylogenetic_result': to_newick(T, labelList),
            'number_of_sample': len(sampel_data)

        }

        return jsonify(result)


    @app.route("/variant_calls", methods = ['GET', 'POST', 'OPTIONS'])
    def __variant_calls():

        if request.method == 'POST':
            input = process_request_vars(request.get_json(silent=True))
        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        if input['chrom'] not in gd.list_chrom:
            return jsonify({
                'success': False, 
                'status': 'error', 
                'message': 'The provided chromosome number '+str(input['chrom'])+' is not included in the variant matrix.'
            })

        
        start = timer()
        slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            count = input['count'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings'],
            with_call_metadata = True
        )
        print("time diff of gd.get_slice_of_variant_calls(): %f", timer() - start)


        if slice.sliced_variant_calls.ndim == 2:
            slice.sliced_variant_calls = slice.sliced_variant_calls.T # transpose GenotypeArray so that samples are in the 1st dimension and not the variant-calls

        if slice.sliced_variant_calls.ndim == 3:
            slice.sliced_variant_calls = slice.sliced_variant_calls.transpose(1, 0, 2) # transpose GenotypeArray so that samples are in the 1st dimension and not the variant-calls

        result = {
            'calls': dict(zip(slice.samples_selected_mapped, slice.sliced_variant_calls.tolist())),
            'calls_metadata': slice.calls_metadata
        }

        return jsonify(result)


    @app.route("/brapi/v2/serverinfo", methods = ['GET', 'OPTIONS'])
    def __serverinfo():

        output = {
            "@context": [
                "https://brapi.org/jsonld/context/metadata.jsonld"
            ],
            "metadata": {
                "datafiles": [],
                "pagination": None,
                "status": [
                    {
                        "message": "Request accepted, response successful",
                        "messageType": "INFO"
                    }
                ]
            },
            "result": {
                "calls": [
                    {
                        "contentTypes": ["application/json"],
                        "dataTypes": ["application/json"],
                        "methods": ["GET",],
                        "service": "serverinfo",
                        "versions": ["2.1"]
                    },
                    {
                        "contentTypes": ["application/json"],
                        "dataTypes": ["application/json"],
                        "methods": ["GET",],
                        "service": "commoncropnames",
                        "versions": ["2.1"]
                    },
                    {
                        "contentTypes": ["application/json"],
                        "dataTypes": ["application/json"],
                        "methods": ["GET",],
                        "service": "allelematrix",
                        "versions": ["2.1"]
                    }
                ],
                "contactEmail": "koenig@ipk-gatersleben.de",
                "documentationURL": "",
                "location": "Germany",
                "organizationName": "IPK Gatersleben",
                "organizationURL": "ipk-gatersleben.de",
                "serverDescription": "DivBrowse",
                "serverName": "DivBrowse BrAPI v2.1 endpoints"
            }
        }

        return jsonify(output)



    @app.route("/brapi/v2/commoncropnames", methods = ['GET', 'OPTIONS'])
    def __commoncropnames():

        output = {
            "@context": [
                "https://brapi.org/jsonld/context/metadata.jsonld"
            ],
            "metadata": {
                "datafiles": [],
                "pagination": {
                    "currentPage": 0,
                    "pageSize": 1000,
                    "totalCount": 10,
                    "totalPages": 1
                },
                "status": [
                    {
                        "message": "Request accepted, response successful",
                        "messageType": "INFO"
                    }
                ]
            },
            "result": {
                "data": [
                    "Barley",
                ]
            }
        }
        return jsonify(output)



    @app.route("/brapi/v2/allelematrix", methods = ['GET', 'POST', 'OPTIONS'])
    def __allelematrix():

        if request.method == 'GET':
            pass

        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        brapi_allelematrix = BrapiAllelematrix(gd, request)

        return jsonify(brapi_allelematrix.get_response_object())



    @app.route("/variants", methods = ['GET', 'POST', 'OPTIONS'])
    def __variants():

        start_all = timer()

        if request.method == 'POST':
            input = process_request_vars(request.get_json(silent=True))
        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        if input['chrom'] not in gd.list_chrom:
            return jsonify({
                'success': False, 
                'status': 'error', 
                'message': 'The provided chromosome number '+str(input['chrom'])+' is not included in the variant matrix.'
            })
        
        log.debug("==== 0 => calculation time: %f", timer() - start_all)

        start = timer()

        slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            count = input['count'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        )

        analysis = Analysis(slice)
        distances = analysis.calc_distance_to_reference(samples = gd.samples)


        # Get the reference nucleotides (as letters ATCG)
        sliced_reference = gd.reference_allele[slice.slice_variant_calls]

        # Get the alternate nucleotides (as letters ATCG)
        sliced_alternates = gd.alternate_alleles[slice.slice_variant_calls]


        start = timer()

        result = {
            'coordinate_first': int(gd.pos[slice.location_start]),
            'coordinate_last': int(gd.pos[slice.location_end - 1]),
            'coordinate_first_next': int(gd.pos[slice.location_end]),
            'coordinate_last_prev': int(gd.pos[slice.location_start - 1]),
            'coordinate_first_chromosome': gd.chrom[slice.location_start],
            'coordinate_last_chromosome': gd.chrom[slice.location_end],
            'variants_coordinates': slice.positions.tolist(),
            'reference': sliced_reference.tolist(),
            'alternates': sliced_alternates.tolist(),
            'hamming_distances_to_reference': distances.tolist()
        }


        #### QUAL #########################
        if 'QUAL' in gd.available_variants_metadata:
            sliced_qual = gd.variants_qual.get_basic_selection(slice.slice_variant_calls)
            slice.variants_summary_stats['vcf_qual'] = sliced_qual.tolist()



        result['per_variant_stats'] = slice.variants_summary_stats

        #### SNPEFF #######################
        if gd.available['snpeff']:
            sliced_ann = gd.callset['variants/ANN'].get_basic_selection(slice.slice_variant_calls)
            
            snpeff_variants = {}
            i = 0
            for snpeff_variant_pos in slice.positions.tolist():
                if isinstance(sliced_ann[i], str):
                    snpeff_variants[snpeff_variant_pos] = sliced_ann[i]
                else:
                    snpeff_variants[snpeff_variant_pos] = sliced_ann[i].tolist()
                i += 1

            result['snpeff_variants_coordinates'] = slice.positions.tolist()
            result['snpeff_variants'] = snpeff_variants


        #### GFF3 ###########################################
        if ad.available['gff3']:
            curr_start = int(gd.pos[slice.location_start])
            curr_end = int(gd.pos[slice.location_end - 1])

            start = timer()
            genes_within_slice = ad.genes.loc[ ( ad.genes['start'] <= curr_start) & (ad.genes['end'] >= curr_end ) ]
            genes_starting_in_slice = ad.genes.loc[ ( ad.genes['start'] >= curr_start) & (ad.genes['start'] <= curr_end ) ]
            genes_ending_in_slice = ad.genes.loc[ ( ad.genes['end'] >= curr_start) & (ad.genes['end'] <= curr_end ) ]
            genes_all_in_slice = pd.concat([genes_within_slice, genes_starting_in_slice, genes_ending_in_slice]).drop_duplicates().reset_index(drop=True)
            genes_all_in_slice = genes_all_in_slice.loc[ (genes_all_in_slice['seqid'] == ad.chrom_gff3_map[input['chrom']]) ]
            calctime = timer() - start
            log.debug("==== time for genes lookup: %f", calctime)
            result['features'] = genes_all_in_slice.to_dict(orient='records')

            #### Nearest gene ##############################
            nearest_gene = ad.get_nearest_gene_start_pos(input['chrom'], int(gd.pos[slice.location_start]))
            result['nearest_feature'] = nearest_gene.to_dict(orient='records')
        

        log.debug("==== output dict creation => calculation time: %f", timer() - start)
        log.debug("==== ALL /variants => calculation time: %f", timer() - start_all)

        return jsonify(result)



    @app.route("/vcf_export_check", methods = ['GET', 'POST', 'OPTIONS'])
    def __vcf_export_check():
        
        if request.method == 'POST':
            input = process_request_vars(request.get_json(silent=True))
        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        if input['chrom'] not in gd.list_chrom:
            return jsonify({
                'success': False, 
                'status': 'error_missing_chromosome', 
                'message': 'The provided chromosome number '+str(input['chrom'])+' is not included in the variant matrix.'
            })

        slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            count = input['count'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        )

        if slice.number_of_variants_in_window_filtered > 5000:
            return jsonify({
                'success': False, 
                'status': 'error_snp_window_too_big', 
                'message': 'The requested genomic window size is bigger than 5000 variants and is therefore too big. Please decrease the window size to not exceed 5000 variants.'
            })

        return jsonify({
            'success': True, 
            'status': 'export_possible',
            'message': slice.number_of_variants_in_window_filtered
        })


    @app.route("/vcf_export", methods = ['GET', 'POST', 'OPTIONS'])
    def __vcf_export():

        if request.method == 'POST':
            input = process_request_vars(request.form.to_dict())
        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        if input['chrom'] not in gd.list_chrom:
            return jsonify({
                'success': False, 
                'status': 'error_missing_chromosome', 
                'message': 'The provided chromosome number '+str(input['chrom'])+' is not included in the variant matrix.'
            })

        slice = gd.get_slice_of_variant_calls(
            chrom = input['chrom'],
            startpos = input['startpos'],
            endpos = input['endpos'],
            samples = input['samples'],
            variant_filter_settings = input['variant_filter_settings']
        )

        vcf_lines_header = gd.get_vcf_header()
        if vcf_lines_header == None:
            # No VCF header files available: fallback to minimal VCF header
            vcf_lines_header = [
                '##fileformat=VCFv4.2',
                #'##fileDate=20190225',
                #'##source=SeqArray_Format_v1.0',
                #'##reference=Morex v2',
                '##FILTER=<ID=PASS,Description="All filters passed">',
                '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
                #'##FORMAT=<ID=DP,Number=.,Type=Integer,Description="Read depth">',
                #'##FORMAT=<ID=DV,Number=.,Type=Integer,Description="Read depth of the alternative allele">'
            ]

        mapped_sample_ids, _ = gd.map_vcf_sample_ids_to_input_sample_ids(gd.samples[slice.samples_mask].astype(str).tolist())
        vcf_line_variants_header = ['#CHROM', 'POS', 'ID', 'REF', 'ALT', 'QUAL', 'FILTER', 'INFO', 'FORMAT'] + mapped_sample_ids
        vcf_lines_header.append("\t".join(vcf_line_variants_header)) 

        ref = gd.reference_allele.get_orthogonal_selection( (slice.filtered_positions_indices) )
        alts = gd.alternate_alleles.get_orthogonal_selection( (slice.filtered_positions_indices) )
        qual = gd.callset['variants/QUAL'].get_orthogonal_selection( (slice.filtered_positions_indices) )
        #mq = callset['variants/MQ'].get_orthogonal_selection( (slice.filtered_positions_indices) )


        vcf_columns = {
            'FORMAT': ['GT']
        }

        # check for DP values and add to FORMAT column
        if 'DP' in gd.available_calldata:
            vcf_columns['FORMAT'].append('DP')


        def __generate():
            
            yield "\n".join(vcf_lines_header) + "\n"


            i = 0
            for pos_idx in slice.filtered_positions_indices.tolist():

                vcf_line = [
                    str(input['chrom']),
                    str(gd.pos[pos_idx]),
                    '.',
                    str(ref[i]),
                    ','.join([ _alt for _alt in (alts[i].astype(str).tolist()) if _alt != '' ]), #','.join([ _alt for _alt in (alts[i].astype(str).tolist()) if _alt != '' ]),
                    str(qual[i]),
                    'NA',
                    '', #'MQ='+str(mq[i]),
                    ":".join(vcf_columns['FORMAT'])
                ]

                if 'samples' in input:
                    #gt_slice = gd.callset['calldata/GT'].get_orthogonal_selection( ([pos_idx], samples_mask, slice(None)) )
                    gt_slice = gd.callset['calldata/GT'].get_orthogonal_selection( ([pos_idx], slice.samples_mask) )

                    if 'DP' in vcf_columns['FORMAT']:
                        dp_slice = gd.callset['calldata/DP'].get_orthogonal_selection( ([pos_idx], slice.samples_mask) )

                else:
                    gt_slice = gd.callset['calldata/GT'].get_orthogonal_selection( ([pos_idx], slice(None), slice(None)) )


                # haploid
                if gt_slice.ndim == 2:
                    ga = allel.HaplotypeArray(gt_slice)
                    gt = ga.to_genotypes(1, copy=True).to_gt()

                # diploid
                if gt_slice.ndim == 3:
                    # Transform each genotype call into the number of non-reference alleles and then transpose it via .T to row-major order
                    ga = allel.GenotypeArray(gt_slice)
                    gt = ga.to_gt()

                gt = gt[0].astype(str).tolist()
                
                if 'DP' in vcf_columns['FORMAT']:
                    dp = dp_slice[0].astype(str).tolist()
                    combined = [call+":"+str(dp[i]) for i, call in enumerate(gt)]
                    gt = combined
                
                vcf_line = vcf_line + gt

                yield "\t".join(vcf_line)+"\n"
                i = i + 1

        return Response(__generate(), mimetype='text/csv', headers={"Content-Disposition":"attachment; filename=custom_export.vcf"})



    @app.route("/gff3_export", methods = ['GET', 'POST', 'OPTIONS'])
    def __gff3_export():

        if request.method == 'POST':
            input = process_request_vars(request.form.to_dict())
        else:
            #raise ApiError('Method not allowed', status_code=405)
            return ''

        if input['chrom'] not in gd.list_chrom:
            return jsonify({
                'success': False, 
                'status': 'error_missing_chromosome', 
                'message': 'The provided chromosome number '+str(input['chrom'])+' is not included in the SNP matrix.'
            })

        curr_start = input['startpos']
        curr_end = input['endpos']

        genes_within_slice = ad.genes.loc[ ( ad.genes['start'] <= curr_start) & (ad.genes['end'] >= curr_end ) ]
        genes_starting_in_slice = ad.genes.loc[ ( ad.genes['start'] >= curr_start) & (ad.genes['start'] <= curr_end ) ]
        genes_ending_in_slice = ad.genes.loc[ ( ad.genes['end'] >= curr_start) & (ad.genes['end'] <= curr_end ) ]
        genes_all_in_slice = pd.concat([genes_within_slice, genes_starting_in_slice, genes_ending_in_slice]).drop_duplicates().reset_index(drop=True)
        genes_all_in_slice = genes_all_in_slice.loc[ (genes_all_in_slice['seqid'] == ad.chrom_gff3_map[input['chrom']]) ]

        genes_all_in_slice = genes_all_in_slice.sort_values('start')
        
        '''
        key_confidence = 'primary_confidence_class'
        if config['gff3']['key_confidence']:
            key_confidence = str(config['gff3']['key_confidence'])

        key_ontology = 'Ontology_term'
        if config['gff3']['key_ontology']:
            key_ontology = str(config['gff3']['key_ontology'])
        '''

        def __generate():

            for index, row in genes_all_in_slice.iterrows():

                gff3_attributes = []
                if row['ID'] != '.':
                    gff3_attributes.append('ID='+str(row['ID']))

                if row['Parent'] != '.':
                    gff3_attributes.append('Parent='+str(row['Parent']))

                if row['description'] != '.':
                    gff3_attributes.append('description='+str(row['description']))

                if row['Ontology_term'] != '.':
                    gff3_attributes.append('Ontology_term='+str(row['Ontology_term']))

                if row['primary_confidence_class'] != '.':
                    gff3_attributes.append('primary_confidence_class='+str(row['primary_confidence_class']))

                _score = str(row['score'])
                _phase = str(row['phase'])

                gff3_line = [
                    str(row['seqid']),
                    str(row['source']),
                    str(row['type']),
                    str(row['start']),
                    str(row['end']),
                    _score if _score != '-1' else '.',
                    str(row['strand']),
                    _phase if _phase != '-1' else '.',
                    ';'.join(gff3_attributes)
                ]

                yield "\t".join(gff3_line)+"\n"

        return Response(__generate(), mimetype='text/csv', headers={"Content-Disposition":"attachment; filename=custom_export.gff3"})





    @app.route("/blast", methods = ['GET', 'POST', 'OPTIONS'])
    def __blast():

        if request.method != 'POST':
            return ''

        if config['blast']['active'] is not True:
            return 'BLAST is not allowed'

        gi = GalaxyInstance(url = config['blast']['galaxy_server_url'], email = config['blast']['galaxy_user'], password = config['blast']['galaxy_pass'])

        json_request_vars = request.get_json(force=True, silent=True)

        blast_types = {
            'ncbi_blastn_wrapper_barley': 'megablast',
            'ncbi_tblastn_wrapper_barley': 'tblastn-fast'
        }

        blast_parameters = {
            'query': str(json_request_vars['query']),
            'database': str(config['blast']['blast_database']),
            #'type': config['blast']['blast_type'],
            'type': blast_types[str(json_request_vars['blast_type'])],
            #'galaxy_tool_id': config['blast']['galaxy_tool_id']
            'galaxy_tool_id': str(json_request_vars['blast_type'])
        }

        histories = gi.histories.get_histories()
        history_id = histories[0]['id']

        paste_content_result = gi.tools.paste_content(blast_parameters['query'], history_id, file_name='blast_query.fasta')
        paste_content_dataset_id = paste_content_result['outputs'][0]['id']

        tool_inputs = (
            inputs().set_dataset_param("query", paste_content_dataset_id, src='hda')
            .set_param('db_opts', 'db')
            .set_param('db_opts|database', [blast_parameters['database']])
            .set_param('blast_type', blast_parameters['type'])
        )
        run_tool_result = gi.tools.run_tool(history_id, blast_parameters['galaxy_tool_id'], tool_inputs)
        result_dataset_id = run_tool_result['outputs'][0]['id']

        blast_chromosome_mapping = config['blast']['blast_result_to_vcf_chromosome_mapping']

        blast_result_dataset = gi.datasets.download_dataset(result_dataset_id)
        blast_result_json = []

        blast_result_lines = blast_result_dataset.decode('utf-8').split("\n")
        for line in blast_result_lines:
            if line != "":
                line_parts = line.split("\t")
                _chromosome_vcf = str(blast_chromosome_mapping[line_parts[1]])
                _single_blast_hit = {
                    'chromosome': _chromosome_vcf,
                    'percentage_of_identical_matches': line_parts[2],
                    'alignment_length': line_parts[3],
                    'number_of_mismatches': line_parts[4],
                    'number_of_gap_openings': line_parts[5],
                    'start_of_alignment_in_query': line_parts[6],
                    'end_of_alignment_in_query': line_parts[7],
                    'start_of_alignment_in_subject': line_parts[8],
                    'end_of_alignment_in_subject': line_parts[9],
                    'e_value': line_parts[10],
                    'bit_score': line_parts[11],
                    'snp_count': gd.count_variants_in_window(_chromosome_vcf, int(line_parts[8]), int(line_parts[9]))
                }
                blast_result_json.append(_single_blast_hit)
        
        return jsonify({
            'success': True,
            'blast_result': str(blast_result_dataset.decode('utf-8')),
            'blast_hits': blast_result_json
        })



    @app.route("/configuration", methods = ['GET', 'POST', 'OPTIONS'])
    def __configuration():

        features = {
            'blast': config['blast']['active'],
            'pca': True,
        }

        samples, _ = gd.map_vcf_sample_ids_to_input_sample_ids(gd.samples.tolist())

        result = {
            'ploidy': gd.ploidy,
            'count_genotypes': gd.count_samples,
            'count_variants': gd.count_variants,
            'count_elements': gd.count_samples * gd.count_variants,
            'chromosomes': gd.list_of_chromosomes,
            'samples': samples,
            'gff3': ad.metadata_gff3,
            'features': features,
            'dataset_descriptions': dict(config['metadata'])
        }

        return jsonify(result)



    @app.route("/chromosomes", methods = ['GET', 'POST', 'OPTIONS'])
    def __chromosomes():
        return jsonify(gd.list_of_chromosomes)


    @app.route("/samples", methods = ['GET', 'POST', 'OPTIONS'])
    def __samples():
        return jsonify(gd.samples.tolist())


    @app.route("/genes", methods = ['GET', 'POST', 'OPTIONS'])
    def __genes():
        r = Response(response=ad.genes_list_json_dumped, status=200, mimetype="application/json")
        r.headers["Content-Type"] = "application/json; charset=utf-8"
        return r
        


    @app.route("/", methods = ['GET', 'POST', 'OPTIONS'])
    def __home():
        return 'Divbrowse server is running'



    @app.errorhandler(ApiError)
    def handle_api_error(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response



    @app.after_request
    def after_request(response):
        header = response.headers
        header['Access-Control-Allow-Origin'] = '*'
        header['Access-Control-Allow-Headers'] = 'Accept, Accept-CH, Accept-Charset, Accept-Datetime, Accept-Encoding, Accept-Ext, Accept-Features, Accept-Language, Accept-Params, Accept-Ranges, Access-Control-Allow-Credentials, Access-Control-Allow-Headers, Access-Control-Allow-Methods, Access-Control-Allow-Origin, Access-Control-Expose-Headers, Access-Control-Max-Age, Access-Control-Request-Headers, Access-Control-Request-Method, Age, Allow, Alternates, Authentication-Info, Authorization, C-Ext, C-Man, C-Opt, C-PEP, C-PEP-Info, CONNECT, Cache-Control, Compliance, Connection, Content-Base, Content-Disposition, Content-Encoding, Content-ID, Content-Language, Content-Length, Content-Location, Content-MD5, Content-Range, Content-Script-Type, Content-Security-Policy, Content-Style-Type, Content-Transfer-Encoding, Content-Type, Content-Version, Cookie, Cost, DAV, DELETE, DNT, DPR, Date, Default-Style, Delta-Base, Depth, Derived-From, Destination, Differential-ID, Digest, ETag, Expect, Expires, Ext, From, GET, GetProfile, HEAD, HTTP-date, Host, IM, If, If-Match, If-Modified-Since, If-None-Match, If-Range, If-Unmodified-Since, Keep-Alive, Label, Last-Event-ID, Last-Modified, Link, Location, Lock-Token, MIME-Version, Man, Max-Forwards, Media-Range, Message-ID, Meter, Negotiate, Non-Compliance, OPTION, OPTIONS, OWS, Opt, Optional, Ordering-Type, Origin, Overwrite, P3P, PEP, PICS-Label, POST, PUT, Pep-Info, Permanent, Position, Pragma, ProfileObject, Protocol, Protocol-Query, Protocol-Request, Proxy-Authenticate, Proxy-Authentication-Info, Proxy-Authorization, Proxy-Features, Proxy-Instruction, Public, RWS, Range, Referer, Refresh, Resolution-Hint, Resolver-Location, Retry-After, Safe, Sec-Websocket-Extensions, Sec-Websocket-Key, Sec-Websocket-Origin, Sec-Websocket-Protocol, Sec-Websocket-Version, Security-Scheme, Server, Set-Cookie, Set-Cookie2, SetProfile, SoapAction, Status, Status-URI, Strict-Transport-Security, SubOK, Subst, Surrogate-Capability, Surrogate-Control, TCN, TE, TRACE, Timeout, Title, Trailer, Transfer-Encoding, UA-Color, UA-Media, UA-Pixels, UA-Resolution, UA-Windowpixels, URI, Upgrade, User-Agent, Variant-Vary, Vary, Version, Via, Viewport-Width, WWW-Authenticate, Want-Digest, Warning, Width, X-Content-Duration, X-Content-Security-Policy, X-Content-Type-Options, X-CustomHeader, X-DNSPrefetch-Control, X-Forwarded-For, X-Forwarded-Port, X-Forwarded-Proto, X-Frame-Options, X-Modified, X-OTHER, X-PING, X-PINGOTHER, X-Powered-By, X-Requested-With'
        return response

    
    return app