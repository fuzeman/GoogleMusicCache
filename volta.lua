if string.match(request.path, '/videoplayback') then
   return string.format( "http://localhost:5000/%s%s", request.host, request.path )
end
