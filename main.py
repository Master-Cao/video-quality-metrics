import time, os, subprocess, sys
from argparse import ArgumentParser, RawTextHelpFormatter
from moviepy.editor import VideoFileClip
from prettytable import PrettyTable
from save_metrics import create_table_plot_metrics, force_decimal_places

if len(sys.argv) == 1:
	print("To see a list of the options available along with descriptions, enter 'python main.py -h'\n")

parser = ArgumentParser(formatter_class=RawTextHelpFormatter)
# Original video path.
parser.add_argument('-ovp', '--original-video-path', type=str, required=True, help='Enter the path of the original '
					'video. A relative or absolute path can be specified. '
					'If the path contains a space, it must be surrounded in double quotes.\n'
					'Example: -ovp "C:/Users/H/Desktop/file 1.mp4"')
# Encoder.
parser.add_argument('-e', '--video-encoder', type=str, default='x264', choices=['x264', 'x265'],
					help='Specify the encoder to use (default: x264).\nExample: -e x265')
# CRF value(s).
parser.add_argument('-crf', '--crf-value', nargs='+', type=int, choices=range(0, 51),
					default=23, help='Specify the CRF value(s) to use.', metavar='CRF_VALUE(s)')
# Preset(s).
parser.add_argument('-p', '--preset', nargs='+', choices=
					['veryslow', 'slower', 'slow', 'medium', 'fast', 'faster', 'veryfast', 'superfast', 'ultrafast'],
					default='medium', help='Specify the preset(s) to use.', metavar='PRESET(s)')
# How many seconds to transcode.
parser.add_argument('-t', '--encoding-time', type=str, help='Encode this many seconds of the video. '
	'If not specified, the whole video will get encoded.\nExample: -t 60')
# Enable phone model?
parser.add_argument('-pm', '--phone-model', action='store_true', help='Enable VMAF phone model.')
# Number of decimal places to use for the data.
parser.add_argument('-dp', '--decimal-places', default=2, help='The number of decimal places to use for the data '
					'in the table (default: 2).\nExample: -dp 3')
# Calculate SSIM?
parser.add_argument('-ssim', '--calculate-ssim', action='store_true', help='Calculate SSIM in addition to VMAF.')
# Calculate psnr?
parser.add_argument('-psnr', '--calculate-psnr', action='store_true', help='Calculate PSNR in addition to VMAF.')
# Disable quality calculation?
parser.add_argument('-dqs', '--disable-quality-stats', action='store_true', help='Disable calculation of '
					'PSNR, SSIM and VMAF; only show encoding time and filesize (improves completion time).')
# No transcoding mode.
parser.add_argument('-ntm', '--no-transcoding-mode', action='store_true', 
					help='Use this mode if you\'ve already transcoded a video and would like its VMAF and (optionally) '
						  'the SSIM and PSNR to be calculated.\n'
						  'Example: -ntm -tvp transcoded.mp4 -ovp original.mp4 -ssim -psnr')
# Transcoded video path (only applicable when using the -ntm mode).
parser.add_argument('-tvp', '--transcoded-video-path', 
					help='The path of the transcoded video (only applicable when using the -ntm mode).')

args = parser.parse_args()

decimal_places = args.decimal_places
# The path of the original video.
original_video = args.original_video_path
# This will be used when comparing the size of the transcoded video to the original (or cut version).
original_video_size = os.path.getsize(original_video) / 1_000_000
# Just the filename.
filename = original_video.split('/')[-1]
# The file extension of the video.
output_ext = os.path.splitext(original_video)[-1][1:]

with VideoFileClip(original_video) as clip:
	fps = str(clip.fps)

print(f'File: {filename}')
print(f'Framerate: {fps} FPS')

# Create a PrettyTable object.
table = PrettyTable()

# Base template for the column names.
table_column_names = ['Encoding Time (s)', 'Size', 'Size Compared to Original']

if not args.disable_quality_stats:
	table_column_names.append('VMAF')
if args.calculate_ssim:
	table_column_names.append('SSIM')
if args.calculate_psnr:
	table_column_names.append('PSNR')
if args.no_transcoding_mode:
	del table_column_names[0]


def separator():
	print('-----------------------------------------------------------------------------------------------------------')


def cut_video():
	cut_version_filename = f'{os.path.splitext(filename)[0]} [{args.encoding_time}s].{output_ext}'
	# Output path for the cut video.
	output_file_path = os.path.join(output_folder, cut_version_filename)
	# The reference file will be the cut version of the video.
	original_video = output_file_path
	# Create the cut version.
	print(f'Cutting the video to a length of {args.encoding_time} seconds...')
	os.system(f'ffmpeg -loglevel warning -y -i {args.original_video_path} -t {args.encoding_time} '
				f'-map 0 -c copy "{output_file_path}"')
	print('Done!')

	original_video_size = os.path.getsize(original_video) / 1_000_000
	time_message = f' for {args.encoding_time} seconds' if int(args.encoding_time) > 1 else 'for 1 second'

	with open(comparison_table, 'w') as f:
		f.write(f'You chose to encode {filename}{time_message} using {args.video_encoder}.\n'
				f'PSNR/SSIM/VMAF values are in the format: Min | Standard Deviation | Mean\n')

	return original_video


def run_libvmaf(transcode_output_path):
	vmaf_options = {
		"model_path": "vmaf_v0.6.1.pkl",
		"phone_model": "1" if args.phone_model else "0",
		"psnr": "1" if args.calculate_psnr else "0",
		"ssim": "1" if args.calculate_ssim else "0",
		"log_path": json_file_path, 
		"log_fmt": "json"
	}
	vmaf_options = ":".join(f'{key}={value}' for key, value in vmaf_options.items())

	subprocess_args = [
		"ffmpeg", "-loglevel", "error", "-stats", "-r", fps, "-i", transcode_output_path,
		"-r", fps, "-i", original_video,
		"-lavfi", "[0:v]setpts=PTS-STARTPTS[dist];[1:v]setpts=PTS-STARTPTS[ref];[dist][ref]"
		f'libvmaf={vmaf_options}', "-f"
		, "null", "-"
	]

	if args.calculate_psnr and args.calculate_ssim:
		end_of_computing_message = ', PSNR and SSIM'
	elif args.calculate_psnr:
		end_of_computing_message = ' and PSNR'
	elif args.calculate_ssim:
		end_of_computing_message = ' and SSIM'
	else:
		end_of_computing_message = ''

	print(f'Computing the VMAF{end_of_computing_message}...')
	subprocess.run(subprocess_args)
	print('Done!')

# If no CRF or preset is specified, the default data types are as str and int, respectively.
if isinstance(args.crf_value, int) and isinstance(args.preset, str):
	separator()
	print('No CRF value(s) or preset(s) specified. Exiting.')
	separator()
	sys.exit()
elif len(args.crf_value) > 1 and isinstance(args.preset, list) and len(args.preset) > 1:
	separator()
	print(f'More than one CRF value AND more than one preset specified. No suitable mode found. Exiting.')
	separator()
	sys.exit()

separator()

# -ntm argument was specified.
if args.no_transcoding_mode:
	seperator()
	output_folder = f'({filename})'
	os.makedirs(output_folder, exist_ok=True)
	comparison_table = os.path.join(output_folder, 'Table.txt')
	table.field_names = table_column_names
	# os.path.join doesn't work with libvmaf's log_path option so we're manually defining the path with slashes.
	json_file_path = f'{output_folder}/QualityMetrics.json'
	graph_filename = 'The variation of the quality of the transcoded video throughout the video'
	transcoded_video = args.transcoded_video_path
	compute_metrics(transcoded_video, output_folder, json_file_path, graph_filename)
	

# args.crf_value is a list when more than one CRF value is specified.
elif isinstance(args.crf_value, list) and len(args.crf_value) > 1:
	separator()
	print('CRF comparison mode activated.')
	crf_values = args.crf_value
	crf_values_string = ', '.join(str(crf) for crf in crf_values)
	preset = args.preset[0] if isinstance(args.preset, list) else args.preset
	print(f'CRF values {crf_values_string} will be compared and the {preset} preset will be used.')
	video_encoder = args.video_encoder
	# Cannot use os.path.join for output_folder as this gives an error like the following:
	# No such file or directory: '(2.mkv)\\Presets comparison at CRF 23/Raw JSON Data/superfast.json'
	output_folder = f'({filename})/CRF comparison at preset {preset}'
	os.makedirs(output_folder, exist_ok=True)
	# The comparison table will be in the following path:
	comparison_table = os.path.join(output_folder, 'Table.txt')
	# Add a CRF column.
	table_column_names.insert(0, 'CRF')
	# Set the names of the columns
	table.field_names = table_column_names

	# The user only wants to transcode the first x seconds of the video.
	if args.encoding_time:
		original_video = cut_video()

	# Transcode the video with each preset.
	for crf in crf_values:
		transcode_output_path = os.path.join(output_folder, f'CRF {crf} at preset {preset}.{output_ext}')
		graph_filename = f'CRF {crf} at preset {preset}'

		subprocess_args = [
			"ffmpeg", "-loglevel", "warning", "-stats", "-y",
			"-i", original_video, "-map", "0",
			"-c:v", f'lib{video_encoder}', "-crf", str(crf), "-preset", preset,
			"-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart", transcode_output_path
		]

		separator()
		print(f'Transcoding the video with CRF {crf}...')
		start_time = time.time()
		subprocess.run(subprocess_args)
		end_time = time.time()
		print('Done!')
		time_to_convert = end_time - start_time
		time_rounded = force_decimal_places(round(time_to_convert, decimal_places), decimal_places)
		transcode_size = os.path.getsize(transcode_output_path) / 1_000_000
		size_compared_to_original = round(((transcode_size / original_video_size) * 100), decimal_places) 
		size_rounded = force_decimal_places(round(transcode_size, decimal_places), decimal_places)
		data_for_current_row = [f'{size_rounded} MB', f'{size_compared_to_original}%']

		if not args.disable_quality_stats:
			os.makedirs(os.path.join(output_folder, 'Raw JSON Data'), exist_ok=True)
			# os.path.join doesn't work with libvmaf's log_path option so we're manually defining the path with slashes.
			json_file_path = f'{output_folder}/Raw JSON Data/CRF {crf}.json'
			preset_string = ','.join(args.preset)
			# The first line of Table.txt:
			with open(comparison_table, 'w') as f:
				f.write(f'PSNR/SSIM/VMAF values are in the format: Min | Standard Deviation | Mean\n')
				f.write(f'Chosen preset(s): {preset_string}\n')
			# Run libvmaf.
			run_libvmaf(transcode_output_path)
			# Run the compute_metrics function.
			create_table_plot_metrics(json_file_path, args, decimal_places, data_for_current_row, graph_filename,
									  time_rounded, table, output_folder, crf)
		# -dqs argument specified
		else: 
			table.add_row([preset, f'{time_rounded}', f'{size_rounded} MB', f'{size_compared_to_original}%'])

# args.preset is a list when more than one preset is specified.
elif isinstance(args.preset, list):
	separator()
	print('Presets comparison mode activated.')
	chosen_presets = args.preset
	presets_string = ', '.join(chosen_presets)
	video_encoder = args.video_encoder
	print(f'Presets {presets_string} will be compared at a CRF of {args.crf_value[0]}.')
	# Cannot use os.path.join for output_folder as this gives an error like the following:
	# No such file or directory: '(2.mkv)\\Presets comparison at CRF 23/Raw JSON Data/superfast.json'
	output_folder = f'({filename})/Presets comparison at CRF {args.crf_value[0]}'
	os.makedirs(output_folder, exist_ok=True)
	comparison_table = os.path.join(output_folder, 'Table.txt')
	table_column_names.insert(0, 'Preset')
	# Set the names of the columns
	table.field_names = table_column_names

	# The user only wants to transcode the first x seconds of the video.
	if args.encoding_time:
		original_video = cut_video()

	# Transcode the video with each preset.
	for preset in chosen_presets:
		transcode_output_path = os.path.join(output_folder, f'{preset}.{output_ext}')
		graph_filename = f"Preset '{preset}'"
		subprocess_args = [
			"ffmpeg", "-loglevel", "warning", "-stats", "-y",
			"-i", original_video, "-map", "0",
			"-c:v", f'lib{video_encoder}', "-crf", str(args.crf_value[0]), "-preset", preset,
			"-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart", transcode_output_path
		]
		separator()
		print(f'Transcoding the video with preset {preset}...')
		start_time = time.time()
		subprocess.run(subprocess_args)
		end_time = time.time()
		print('Done!')
		time_to_convert = end_time - start_time
		time_rounded = force_decimal_places(round(time_to_convert, decimal_places), decimal_places)
		transcode_size = os.path.getsize(transcode_output_path) / 1_000_000
		size_compared_to_original = round(((transcode_size / original_video_size) * 100), decimal_places) 
		size_rounded = force_decimal_places(round(transcode_size, decimal_places), decimal_places)
		data_for_current_row = [f'{size_rounded} MB', f'{size_compared_to_original}%']

		if not args.disable_quality_stats:
			os.makedirs(os.path.join(output_folder, 'Raw JSON Data'), exist_ok=True)
			# os.path.join doesn't work with libvmaf's log_path option so we're manually defining the path with slashes.
			json_file_path = f'{output_folder}/Raw JSON Data/{preset}.json'
			preset_string = ','.join(args.preset)
			# The first line of Table.txt:
			with open(comparison_table, 'w') as f:
				f.write(f'PSNR/SSIM/VMAF values are in the format: Min | Standard Deviation | Mean\n')
				f.write(f'Chosen preset(s): {preset_string}\n')
			# Run libvmaf.
			run_libvmaf(transcode_output_path)
			# Run the compute_metrics function.
			create_table_plot_metrics(json_file_path, args, decimal_places, data_for_current_row, graph_filename,
									  time_rounded, table, output_folder, preset)
	
		# -dqs argument specified
		else:
			table.add_row([preset, f'{time_rounded}', f'{size_rounded} MB', f'{size_compared_to_original}%'])

# Write the table to the Table.txt file.
with open(comparison_table, 'a') as f:
	f.write(table.get_string())

separator()
print(f'All done! Check out the ({filename}) folder.')
