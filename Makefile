debug:
	docker build -t observations .
	docker run -it -v ~/Dropbox/Observations/:/app/data -p 80:5000 observations