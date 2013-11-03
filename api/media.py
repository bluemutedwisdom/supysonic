# coding: utf-8

from flask import request, send_file, Response
import os.path
from PIL import Image
import subprocess
import shlex

import config, scanner
from web import app
from db import Track, Folder, User, now, session
from api import get_entity

def prepare_transcoding_cmdline(base_cmdline, input_file, input_format, output_format, output_bitrate):
	if not base_cmdline:
		return None

	return base_cmdline.replace('%srcpath', '"'+input_file+'"').replace('%srcfmt', input_format).replace('%outfmt', output_format).replace('%outrate', str(output_bitrate))

def transcode(process):
	for chunk in iter(process, ''):
		yield chunk

@app.route('/rest/stream.view', methods = [ 'GET', 'POST' ])
def stream_media():
	status, res = get_entity(request, Track)

	if not status:
            return res

	maxBitRate, format, timeOffset, size, estimateContentLength = map(request.args.get, [ 'maxBitRate', 'format', 'timeOffset', 'size', 'estimateContentLength' ])
	if format:
		format = format.lower()

	do_transcoding = False
	src_suffix = res.suffix()
	dst_suffix = res.suffix()
	dst_bitrate = res.bitrate
	dst_mimetype = res.content_type

	if format != 'raw': # That's from API 1.9.0 but whatever
		if maxBitRate:
			try:
				maxBitRate = int(maxBitRate)
			except:
				return request.error_formatter(0, 'Invalid bitrate value')

			if dst_bitrate > maxBitRate and maxBitRate != 0:
				do_transcoding = True
				dst_bitrate = maxBitRate

		if format and format != src_suffix:
			do_transcoding = True
			dst_suffix = format
			dst_mimetype = scanner.get_mime(dst_suffix)

	if not format and src_suffix == 'flac':
		dst_suffix = 'ogg'
		dst_bitrate = 320
		dst_mimetype = scanner.get_mime(dst_suffix)
		do_transcoding = True

	if do_transcoding:
		transcoder = config.get('transcoding', 'transcoder_{}_{}'.format(src_suffix, dst_suffix))

		decoder = config.get('transcoding', 'decoder_' + src_suffix) or config.get('transcoding', 'decoder')
		encoder = config.get('transcoding', 'encoder_' + dst_suffix) or config.get('transcoding', 'encoder')

		if not transcoder and (not decoder or not encoder):
			transcoder = config.get('transcoding', 'transcoder')
			if not transcoder:
				return request.error_formatter(0, 'No way to transcode from {} to {}'.format(src_suffix, dst_suffix))

		transcoder, decoder, encoder = map(lambda x: prepare_transcoding_cmdline(x, res.path, src_suffix, dst_suffix, dst_bitrate), [ transcoder, decoder, encoder ])

		decoder = shlex.split(decoder)
		encoder = shlex.split(encoder)

		if '|' in shlex.split(transcoder):
			transcoder = shlex.split(transcoder)
			pipe_index = transcoder.index('|')
			decoder = transcoder[:pipe_index]
			encoder = transcoder[pipe_index+1:]
			transcoder = None


		try:
			if transcoder:
				app.logger.warn('single line transcode: '+transcoder)
				proc = subprocess.Popen(shlex.split(transcoder), stdout = subprocess.PIPE, shell=False)
			else:
				app.logger.warn('multi process transcode: ')
				app.logger.warn('decoder' + str(decoder))
				app.logger.warn('encoder' + str(encoder))
				dec_proc = subprocess.Popen(decoder, stdout = subprocess.PIPE, shell=False)
				proc = subprocess.Popen(encoder, stdin = dec_proc.stdout, stdout = subprocess.PIPE, shell=False)

			response = Response(transcode(proc.stdout.readline), 200, {'Content-Type': dst_mimetype})
		except:
			return request.error_formatter(0, 'Error while running the transcoding process')

	else:
		app.logger.warn('no transcode')
		response = send_file(res.path, mimetype = dst_mimetype)

	res.play_count = res.play_count + 1
	res.last_play = now()
	request.user.last_play = res
	request.user.last_play_date = now()
	session.commit()

	return response

@app.route('/rest/download.view', methods = [ 'GET', 'POST' ])
def download_media():
	status, res = get_entity(request, Track)
	if not status:
		return res

	return send_file(res.path)

@app.route('/rest/getCoverArt.view', methods = [ 'GET', 'POST' ])
def cover_art():
	status, res = get_entity(request, Folder)
	if not status:
		return res

	if not res.has_cover_art or not os.path.isfile(os.path.join(res.path, 'cover.jpg')):
		return request.error_formatter(70, 'Cover art not found')

	size = request.args.get('size')
	if size:
		try:
			size = int(size)
		except:
			return request.error_formatter(0, 'Invalid size value')
	else:
		return send_file(os.path.join(res.path, 'cover.jpg'))

	im = Image.open(os.path.join(res.path, 'cover.jpg'))
	if size > im.size[0] and size > im.size[1]:
		return send_file(os.path.join(res.path, 'cover.jpg'))

	size_path = os.path.join(config.get('base', 'cache_dir'), str(size))
	path = os.path.join(size_path, str(res.id))
	if os.path.exists(path):
		return send_file(path)
	if not os.path.exists(size_path):
		os.makedirs(size_path)

	im.thumbnail([size, size], Image.ANTIALIAS)
	im.save(path, 'JPEG')
	return send_file(path)

