%setdefault('stylesheet', None)
%setdefault('navigation', False)
<!DOCTYPE html>
<html lang="en">
<head>
  <title>{{!doc_attributes["name"]}}</title>
  <meta charset="utf-8" />
  <meta http-equiv="content-type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  % if is_doc:
  %   tmpRef='../'
  % else:
  %   tmpRef=''
  % end
  <link rel="stylesheet" href="{{baseurl}}{{tmpRef}}template/bootstrap.min.css" />
  <link rel="stylesheet" href="{{baseurl}}{{tmpRef}}template/general.css" />
  {{! '<link type="text/css" rel="stylesheet" href="%s" />'%(baseurl+tmpRef+'template/'+stylesheet) if stylesheet else "" }}
  <script src="{{baseurl}}{{tmpRef}}template/tex-mml-chtml.js" id="MathJax-script" async></script>
  <script>
  MathJax = {
    tex: {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']]
    },
    svg: { fontCache: 'global' }
  };
  </script>
</head>
<body>
  {{!base}}
</body>
</html>
