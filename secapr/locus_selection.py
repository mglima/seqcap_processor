# encoding: utf-8
'''
Extract the n loci with the best read-coverage from you reference-based assembly (bam-files)
'''
import os
import glob
import re
import subprocess
import csv
import pandas as pd
import pickle
from Bio import SeqIO
from .utils import CompletePath


# Get arguments
def add_arguments(parser):
	parser.add_argument(
		'--input',
		required=True,
		action=CompletePath,
		default=None,
		help='The folder with the results of the reference based assembly or the phasing results.'
	)
	parser.add_argument(
		'--output',
		required=True,
		action=CompletePath,
		default=None,
		help='The output directory where results will be safed.'
	)
	parser.add_argument(
		'--n',
		type=int,
		default=30,
		help='The n loci that are best represented accross all samples will be extracted.'
	)
	parser.add_argument(
		'--read_cov',
		type=int,
		default=3,
		help='The threshold for what average read coverage the selected target loci should at least have.'
	)


def get_bam_path_dict(input_dir):
    type_input = ''
    subdirs = os.listdir(input_dir)
    sample_bam_dict = {}
    for subd in subdirs:
        if subd.endswith('_remapped'):
            type_input = 'unphased'
            sample_id = subd.split('_')[0]
            bam = '%s/%s/%s*sorted.bam' %(input_dir,subd,sample_id)
            target_files = glob.glob(bam)
            unphased_bam = target_files[0]
            if len(target_files) > 1:
                print('Found multiple files matching the search, but there should only be one bam file containing the re-mapped reads. Please remove any non-relevant bam-files from target directory and run this function again.')
                print(target_files)
                exit()
            else:
                sample_bam_dict.setdefault(subd,[])
                sample_bam_dict[subd].append(unphased_bam)
            

        elif subd.endswith('_phased'):
            type_input = 'phased'
            sample_id = subd.split('_')[0]
            bam = '%s/%s/phased_bam_files/%s*sorted_allele_[0,1].bam' %(input_dir,subd,sample_id)
            target_files = glob.glob(bam)
            allele_0_bam = target_files[0]
            allele_1_bam = target_files[1]
            if len(target_files) > 2:
                print('Found multiple files matching the search, but there should only be one bam file per allele containing the re-mapped reads. Please remove any non-relevant bam-files from target directory and run this function again.')
                print(target_files)
                exit()
            else:
                sample_bam_dict.setdefault(subd,[])
                sample_bam_dict[subd].append(allele_0_bam)
                sample_bam_dict[subd].append(allele_1_bam)
    return sample_bam_dict, type_input


def get_bam_read_cov(bam,output_folder):
    bam_name = bam.split("/")[-1]
    sample_base = bam_name.split(".bam")[0]
    sample_base = sample_base.split("_")[0]
    sample_base = sample_base.split(".")[0]
    print ('Reading read-depth info for %s.........' %sample_base)
    sample_dir = os.path.join(output_folder,'%s_locus_selection' %sample_base)
    if not os.path.exists(sample_dir):
        os.makedirs(sample_dir)


    get_read_depth = ["samtools", "depth", bam]
    read_depth_file = os.path.join(sample_dir,"%s_read_depth_per_position.txt" %sample_base)

    with open(read_depth_file, 'w') as logfile:
        sp1 = subprocess.Popen(get_read_depth, shell=False, stderr = subprocess.STDOUT, stdout=logfile)
        sp1.wait()
    return sample_dir,read_depth_file


def get_complete_loci_list(subfolder_file_dict):
    print('Generating locus database.........')
    locus_list = []
    for subfolder in subfolder_file_dict:
        read_depth_file = subfolder_file_dict[subfolder]
        #sample_id = read_depth_file.split('/')[-1].split('_')[0]
        with open(read_depth_file, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            reader = list(reader)
            for row in reader:
                locus_name = row[0]
                if locus_name not in locus_list:
                    locus_list.append(locus_name)
    return sorted(locus_list)


def summarize_read_depth_files(subfolder,read_depth_file,complete_locus_list,locus_dict_all_samples,sample_list,reference):
    sample_id = read_depth_file.split('/')[-1].split('_')[0]
    sample_list.append(sample_id)
    print ('Calculating coverage for all loci from bam files for %s.........' %sample_id)
    reference_library = SeqIO.parse(reference, "fasta")
    locus_original_length_dict = {}
    for reference in reference_library:
        reference_locus = reference.name
        reference_sequence = reference.seq
        locus_length = len(str(reference_sequence))
        locus_original_length_dict.setdefault(reference_locus,locus_length)
    sample_loci_dict = {}
    with open(read_depth_file, 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        reader = list(reader)
        for row in reader:
            locus = row[0]
            locus_list = locus.split("_")[:3]
            locus_name = "_".join(locus_list)
            position = row[1]
            coverage = int(row[2])
            sample_loci_dict.setdefault(locus_name,[])
            sample_loci_dict[locus_name].append(coverage)
    
    for locus_name in complete_locus_list:
        if locus_name in sample_loci_dict:
            avg_read_depth = float(sum(sample_loci_dict[locus_name]))/float(locus_original_length_dict[locus_name])
            locus_dict_all_samples.setdefault(locus_name,[])
            locus_dict_all_samples[locus_name].append(avg_read_depth)
        else:
            avg_read_depth = 0.0
            locus_dict_all_samples.setdefault(locus_name,[])
            locus_dict_all_samples[locus_name].append(avg_read_depth)

    return locus_dict_all_samples 


def extract_best_loci(subfolder_file_dict,sample_bam_dict,output_folder,n,threshold,input_type):
    output_subfolder_dict = {}
    for key in subfolder_file_dict:
        sample_id = key.split('/')[-1].split('_')[0]
        output_subfolder_dict.setdefault(sample_id,key)
    sample_subfolder_dict = {}
    for key in sample_bam_dict:
        sample_id = key.split('_')[0]
        sample_subfolder = '/'.join(sample_bam_dict[key][0].split('/')[0:-1])
        sample_subfolder_dict.setdefault(sample_id,sample_subfolder)
    
    # Read the coverage overview file and select the ebst loci
    coverage_all_samples = pd.read_csv("%s/average_cov_per_locus.txt" %output_folder, sep = '\t')
    
    # Return boolean for every field, depending on if its greater than the threshold
    thres_test = coverage_all_samples.ix[:,1:]>threshold
    # Extract only those rows for which all fields returned 'True' and store in new df
    selected_rows = pd.DataFrame([])
    for line in thres_test.iterrows():
        line = line[1]
        if line.all():
            selected_rows = selected_rows.append(line)
    # Store all indices of the selected data (selected_rows) in a list
    indeces = list(selected_rows.index.get_values())
    # Use indices to extract rows from oriignal df and create new one from it
    loci_passing_test = coverage_all_samples.iloc[indeces,:].copy()
    list_of_good_loci = list(loci_passing_test.locus)
    # Calculate the read-depth sum across all samples for each locus and store as new column in df 
    loci_passing_test['sum_per_locus'] = loci_passing_test.ix[:,1:].sum(axis=1)
    # Sort the df by the 'sum' column to have the best covered loci on top
    loci_passing_test.sort_values('sum_per_locus', axis=0, ascending=False, inplace=True)
    # select best n rows
    selection = pd.DataFrame([])
    if len(loci_passing_test) >= n:
        selection = loci_passing_test[:n].copy()
    else:
        selection = loci_passing_test[:].copy()
    #***************************
    # This was a previous solution, but not including a control for having at least [threshold] avg read coverage
    #data_cols = coverage_all_samples.ix[:,1:]
    #sum_per_sample = data_cols.sum()
    #coverage_all_samples['sum_per_locus'] = data_cols.sum(axis=1)
    #sorted_cov_df = coverage_all_samples.sort_values(['sum_per_locus'],ascending=False).copy()
    #selection = sorted_cov_df[0:n]
    #***************************

    no_of_loci = len(coverage_all_samples)
    # An output for knowing which samples worked best
    avg_read_cov_across_all_loci = selection.sum_per_locus/no_of_loci
    avg_read_cov_across_all_loci.sort_values(ascending=False).to_csv('%s/average_read_coverage_across_all_loci_per_sample.txt' %output_folder, sep = '\t', index = True,header=False)

    # Create output file with read-depth overview of only the selected loci
    selection_out = selection.copy()
    #selection_out.remove('sum_per_locus')
    selection_out.to_csv('%s/overview_selected_loci.txt' %output_folder,index=False,sep='\t')
    target_loci = list(selection.locus)
    # Now iterate through samples
    for sample in sample_subfolder_dict:
        sequence_collection = []
        fasta = '%s/%s*.fasta' %(sample_subfolder_dict[sample],sample)
        target_files = glob.glob(fasta)
        sequence_file = target_files[0]
        sequence_library = SeqIO.parse(sequence_file, "fasta")
        for sequence in sequence_library:
            locus_name = sequence.name
            locus_name_corrected = re.sub('_%s'%sample, '', locus_name)
            #locus_sequence = sequence.seq
            if locus_name_corrected in target_loci:
                sequence_collection.append(sequence)
        SeqIO.write(sequence_collection, "%s/%s_%s_selected_sequences.fasta" %(output_subfolder_dict[sample],sample,input_type), "fasta")
        
        # Now produce a new bam-file
        bam = '%s/%s*.bam' %(sample_subfolder_dict[sample],sample)
        target_files = glob.glob(bam)
        bam_file = target_files[0]
        target_loci_string = ' '.join(target_loci)
        bam_output_file = os.path.join(output_subfolder_dict[sample],"%s_%s_selected_loci.bam" %(sample,input_type))
        select_from_bam = 'samtools view %s %s > %s' %(bam_file,target_loci_string,bam_output_file)
        os.system(select_from_bam)
    return target_loci


def main(args):
    input_dir = args.input
    output_folder = args.output
    n = args.n
    threshold = args.read_cov

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    else:
        raise IOError("The directory {} already exists.  Please check and remove by hand.".format(output_folder))
    # Create a dictionary containing the bam-file paths for each sample and tell if data is phased or unphased
    sample_bam_dict, input_type = get_bam_path_dict(input_dir)

    if input_type == 'unphased':
        subfolder_list = []
        subfolder_file_dict = {}
        reference_file_dict = {}
        # iterating through samples
        for key in sample_bam_dict:
            if key.endswith('_remapped'):
                sample = key.split('_')[0]
                path = os.path.join(input_dir,key)
                path2 = os.path.join(path,'tmp')
                reference_pickle = os.path.join(path2,'%s_reference.pickle' %sample)
                reference_file_dict.setdefault(sample,reference_pickle)        
                bam = sample_bam_dict[key][0]
                sample_dir, read_depth_file = get_bam_read_cov(bam,output_folder)
                subfolder_file_dict.setdefault(sample_dir,read_depth_file)

        locus_list = get_complete_loci_list(subfolder_file_dict)
        locus_dict_all_samples = {}
        sample_id_list = []
        for subfolder in subfolder_file_dict:
            sample = subfolder.split('/')[-1].split('_')[0]
            reference = ''
            reference_pickle = reference_file_dict[sample]
            with open(reference_pickle, 'rb') as handle:
                reference = pickle.load(handle)
            read_depth_file = subfolder_file_dict[subfolder]
            locus_dict_all_samples = summarize_read_depth_files(subfolder,read_depth_file,locus_list,locus_dict_all_samples,sample_id_list,reference)

        output_dict = {}
        # Create a separate list for each column in the final csv file
        final_locus_list = ['locus']
        for locus in locus_dict_all_samples:
            final_locus_list.append(locus)
        output_dict.setdefault('column1',final_locus_list)

        for sample in sample_id_list:
            index = sample_id_list.index(sample)
            key_int = 2+index
            key_name = 'column%i' %key_int
            output_dict.setdefault(key_name,[sample])
            for locus in locus_dict_all_samples:
                read_depth = locus_dict_all_samples[locus][index]
                output_dict[key_name].append(read_depth)

        final_data_list = []

        for column in sorted(output_dict):
            data = output_dict[column]
            final_data_list.append(data)

        output = open("%s/average_cov_per_locus.txt" %output_folder, "w")
        outlog=csv.writer(output, delimiter='\t')
        transformed_data = zip(*final_data_list)
        for row in transformed_data:
            outlog.writerow(row)
        target_loci = extract_best_loci(subfolder_file_dict,sample_bam_dict,output_folder,n,threshold,input_type)

    elif input_type == 'phased':
        phased = True
        exit("This function does currently not support phased data. Will be upgraded soon!")
