"""Structural checks for the explicitly virtual two-profile integration test."""
import hashlib, io, json, pathlib, posixpath, re, struct, zipfile
import xml.etree.ElementTree as ET

BASE = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = BASE.parents[1] / '.local/advanced-tests/session3'
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
reports=[]
for family in ('kird','kedi'):
    source=OUTPUT/(family+'-virtual-diagnostic.pptx')
    proto=json.loads((BASE/'fixtures'/(family+'-virtual-proto.json')).read_text())
    with zipfile.ZipFile(source) as archive:
        assert archive.testzip() is None
        names=archive.namelist()
        for name in names:
            if name.endswith('.xml') or name.endswith('.rels'):
                root=ET.fromstring(archive.read(name))
                if name.endswith('.rels'):
                    parent=posixpath.dirname(name)
                    package_dir=posixpath.dirname(parent) if parent.endswith('_rels') else ''
                    for rel in root:
                        if rel.attrib.get('TargetMode')=='External':
                            continue
                        target=rel.attrib['Target']
                        resolved=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(package_dir,target))
                        assert resolved in names,(name,target,resolved)
        presentation=ET.fromstring(archive.read('ppt/presentation.xml'))
        size=presentation.find('p:sldSz',NS)
        expected=[round(proto['width']*914400),round(proto['height']*914400)]
        assert [int(size.attrib['cx']),int(size.attrib['cy'])]==expected
        slides=sorted(n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
        assert len(slides)==2
        slide_reports=[]
        for number,name in enumerate(slides,1):
            root=ET.fromstring(archive.read(name))
            texts=[e.text for e in root.findall('.//a:t',NS) if e.text]
            assert any('가상' in text and '진단' in text and '비납품' in text for text in texts)
            assert any('#1' in text for text in texts)
            notes=ET.fromstring(archive.read(f'ppt/notesSlides/notesSlide{number}.xml'))
            note_text=''.join(e.text or '' for e in notes.findall('.//a:t',NS))
            assert 'diagnosticOnly' in note_text and '"id":1' in note_text
            counts={'native_shapes':len(root.findall('.//p:sp',NS)),
                    'native_tables':len(root.findall('.//a:tbl',NS)),
                    'native_charts':len(root.findall('.//c:chart',NS)),
                    'pictures':len(root.findall('.//p:pic',NS))}
            if number==1:
                assert counts['native_tables']==1 and counts['native_charts']==1 and counts['pictures']==1
            else:
                assert counts['pictures']==0
                for label in ('원고','장면','화면'):assert label in texts
                assert counts['native_shapes']>=13
            slide_reports.append({'slide':number,**counts,'native_text_runs':len(texts),'page_cue_reset_to_one':True})
        charts=[n for n in names if re.fullmatch(r'ppt/charts/chart\d+\.xml',n)]
        assert len(charts)==1
        chart=ET.fromstring(archive.read(charts[0]))
        values=[e.text for e in chart.findall('.//c:val/c:numRef/c:numCache/c:pt/c:v',NS)]
        assert values==['2','4','3'],values
        workbooks=[n for n in names if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
        assert len(workbooks)==1
        with zipfile.ZipFile(io.BytesIO(archive.read(workbooks[0]))) as workbook:
            assert workbook.testzip() is None
        svgs=[n for n in names if n.endswith('.svg')]
        assert len(svgs)==1
        preview=re.sub(r'-(\d+)\.svg$',lambda m:'-'+str(int(m[1])-1)+'.png',svgs[0])
        png=archive.read(preview)
        assert png[:8]==b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II',png[16:24])==(120,60)
        report={'family':family,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'size_emu':expected,'slide_count':len(slides),'slides':slide_reports,'chart_cached_values':values,'embedded_workbook_crc_pass':True,'svg_preserved':True,'svg_png_fallback_dimensions':[120,60],'all_xml_parsed':True,'all_internal_relationships_resolve':True,'zip_crc_pass':True}
        reports.append(report)
(OUTPUT/'structural-verification.json').write_text(json.dumps({'passed':True,'diagnosticOnly':True,'reports':reports},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':True,'files':len(reports),'report':str(OUTPUT/'structural-verification.json')}))
