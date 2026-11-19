import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.shared.cotizaciones_config import ConfiguracionB2B, descuento_b2b
from backend.shared.security import create_access_token
from backend.services.clientes.app.main import app as clientes_app
from backend.services.clientes.app import routers_corporativos
from backend.services.ordenes.app.main import app as ordenes_app
from backend.services.ordenes.app import routers_cotizaciones, cotizaciones
from backend.tests.test_tarjetas_regalo import postgres, LocalSupabase


class SQLClient(LocalSupabase):
    def table(self, name): return Query(self.conectar, name)
    def rpc(self, name, params=None): return super().rpc(name,params or {})


class Query:
    def __init__(self, connect, table):
        self.connect, self.table = connect, table
        self.columns, self.filters, self.orders = '*', [], []
        self.take, self.skip, self.counting, self.operation = 1000, 0, False, 'select'
        self.disjunction = []
    def select(self, columns='*', **kwargs): self.columns=columns; self.counting=kwargs.get('count')=='exact'; return self
    def eq(self, key, value): self.filters.append((key,'=',value)); return self
    def in_(self, key, value): self.filters.append((key,'in',value)); return self
    def lt(self,key,value): self.filters.append((key,'<',value)); return self
    def lte(self,key,value): self.filters.append((key,'<=',value)); return self
    def gte(self,key,value): self.filters.append((key,'>=',value)); return self
    def ilike(self,key,value): self.filters.append((key,'ILIKE',value)); return self
    def or_(self,value): self.disjunction=[part.split('.',2) for part in value.split(',')]; return self
    def order(self,key,desc=False): self.orders.append((key,desc)); return self
    def limit(self,n): self.take=n; return self
    def range(self,start,end): self.skip,self.take=start,end-start+1; return self
    def insert(self,data): self.operation,self.data='insert',data; return self
    def update(self,data): self.operation,self.data='update',data; return self
    def delete(self): self.operation='delete'; return self
    def execute(self):
        from psycopg2 import sql
        from psycopg2.extras import Json, RealDictCursor
        wrap=lambda v: Json(v) if isinstance(v,(dict,list)) else v
        conn=self.connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                table=sql.Identifier(self.table)
                where=sql.SQL(' WHERE TRUE'); params=[]
                for key,op,value in self.filters:
                    where+=sql.SQL(' AND {} = ANY(%s::uuid[])' if op=='in' else ' AND {} '+op+' %s').format(sql.Identifier(key))
                    params.append(value)
                if self.disjunction:
                    parts=[]
                    for key,op,value in self.disjunction:
                        if op=='is': parts.append(sql.SQL('{} IS NULL').format(sql.Identifier(key)))
                        else: parts.append(sql.SQL('{} >= %s').format(sql.Identifier(key))); params.append(value)
                    where+=sql.SQL(' AND (')+sql.SQL(' OR ').join(parts)+sql.SQL(')')
                if self.operation=='insert':
                    rows=[]
                    for record in self.data if isinstance(self.data,list) else [self.data]:
                        cur.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(table,
                            sql.SQL(',').join(map(sql.Identifier,record)),sql.SQL(',').join(sql.Placeholder() for _ in record)),[wrap(v) for v in record.values()])
                        rows.extend(cur.fetchall())
                    return SimpleNamespace(data=json.loads(json.dumps(rows,default=str)))
                if self.operation=='update':
                    cur.execute(sql.SQL('UPDATE {} SET ').format(table)+sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in self.data)+where+sql.SQL(' RETURNING *'),[wrap(v) for v in self.data.values()]+params)
                    return SimpleNamespace(data=json.loads(json.dumps(cur.fetchall(),default=str)))
                if self.operation=='delete':
                    cur.execute(sql.SQL('DELETE FROM {}').format(table)+where+sql.SQL(' RETURNING *'),params)
                    return SimpleNamespace(data=json.loads(json.dumps(cur.fetchall(),default=str)))
                cur.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(table)+where,params)
                count=cur.fetchone()['n']
                cols=sql.SQL('*') if self.columns=='*' else sql.SQL(',').join(map(sql.Identifier,self.columns.split(',')))
                query=sql.SQL('SELECT {} FROM {}').format(cols,table)+where
                if self.orders: query+=sql.SQL(' ORDER BY ')+sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(k),sql.SQL('DESC' if d else 'ASC')) for k,d in self.orders)
                cur.execute(query+sql.SQL(' LIMIT %s OFFSET %s'),params+[self.take,self.skip])
                return SimpleNamespace(data=json.loads(json.dumps(cur.fetchall(),default=str)),count=count)
        finally: conn.close()


@pytest.fixture(scope='module')
def db(postgres):
    conn=postgres()
    migrations=Path(__file__).parents[1]/'db/migrations'
    with conn.cursor() as cur:
        cur.execute('''
          CREATE TYPE tipo_cliente_enum AS ENUM ('retail','corporativo_b2b');
          CREATE TYPE estado_cotizacion_enum AS ENUM ('emitida','vencida');
          CREATE TABLE perfiles_clientes(id UUID PRIMARY KEY DEFAULT gen_random_uuid(),user_id UUID,
            nombre_completo TEXT NOT NULL,razon_social TEXT,nit_ci TEXT,email TEXT UNIQUE NOT NULL,telefono TEXT,
            tipo_cliente tipo_cliente_enum,created_at TIMESTAMPTZ DEFAULT now());
          CREATE TABLE productos(id UUID PRIMARY KEY,nombre TEXT,estado TEXT);
          ALTER TABLE variantes ADD COLUMN sku TEXT,ADD COLUMN nombre_variante TEXT,ADD COLUMN precio NUMERIC;
          CREATE TABLE listas_precios(id UUID PRIMARY KEY,canal TEXT,tipo_cliente TEXT,activo BOOLEAN);
          CREATE TABLE precios_items(variante_id UUID,lista_precio_id UUID,precio NUMERIC,fecha_inicio TIMESTAMPTZ,fecha_fin TIMESTAMPTZ);
          CREATE TABLE cotizaciones_b2b(id UUID PRIMARY KEY DEFAULT gen_random_uuid(),codigo_cotizacion TEXT,
            cliente_id UUID,gerente_id UUID,subtotal NUMERIC,descuento_porcentaje NUMERIC,total NUMERIC,
            vigencia_hasta DATE,estado estado_cotizacion_enum,created_at TIMESTAMPTZ DEFAULT now());
          CREATE TABLE cotizacion_items(cotizacion_id UUID,variante_id UUID,cantidad INT,precio_unitario NUMERIC,total_linea NUMERIC);
          CREATE TABLE audit_logs(id UUID PRIMARY KEY,user_id UUID,user_role TEXT,ip_address TEXT,action TEXT,entity TEXT,
            entity_id UUID,payload_before JSONB,payload_after JSONB,created_at TIMESTAMPTZ DEFAULT now());
        ''')
        for name in ['20261107_kan_194_cotizaciones_volumen.sql','20261110040056_auditoria_estructurada.sql','20261110061159_empresas_y_descuentos_b2b.sql']:
            cur.execute((migrations/name).read_text(encoding='utf-8'))
    conn.close()
    return SQLClient(postgres),postgres


def auth(role='administrador',**extra):
    return {'Authorization':'Bearer '+create_access_token({'sub':str(uuid4()),'role':role,**extra})}


def empresa():
    return {'nit_ci':str(uuid4().int)[:12],'razon_social':'Empresa de prueba B2B','email':uuid4().hex+'@example.com'}


@pytest.fixture
def system(db,monkeypatch):
    client,connect=db
    conn=connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE cotizaciones_configuracion SET version=1,configuracion=%s",(json.dumps({'habilitado':True,'escalas':[{'minimo_unidades':5,'descuento_porcentaje':5},{'minimo_unidades':10,'descuento_porcentaje':10},{'minimo_unidades':20,'descuento_porcentaje':15}]}),))
    conn.close()
    monkeypatch.setattr(routers_corporativos,'get_supabase_admin_client',lambda:client)
    monkeypatch.setattr(routers_cotizaciones,'get_supabase_admin_client',lambda:client)
    return SimpleNamespace(client=client,connect=connect,companies=TestClient(clientes_app),quotes=TestClient(ordenes_app),headers=auth())


def test_alta_empresa_y_busqueda_por_nit_sin_usuario_auth(system):
    payload=empresa()
    response=system.companies.post('/api/v1/clientes/corporativos',json=payload,headers=system.headers)
    assert response.status_code==201,response.text
    data=response.json()
    stored=system.client.table('perfiles_clientes').select('*').eq('id',data['cliente']['id']).execute().data[0]
    assert stored['tipo_cliente']=='corporativo_b2b' and stored['user_id'] is None
    assert stored['nombre_completo']==payload['razon_social']
    found=system.quotes.get('/api/v1/cotizaciones/clientes',params={'q':payload['nit_ci']},headers=system.headers)
    assert found.status_code==200 and found.json()[0]['id']==stored['id']
    repeated=system.companies.post('/api/v1/clientes/corporativos',json={**payload,'razon_social':'No sobrescribir'},headers=system.headers)
    assert repeated.status_code==200 and repeated.json()['creado'] is False
    assert repeated.json()['cliente']['razon_social']==payload['razon_social']


def test_registro_concurrente_no_duplica_empresas(system):
    payload=empresa()
    def create(): return system.client.rpc('registrar_empresa_b2b',{'p_datos':payload}).execute().data
    with ThreadPoolExecutor(6) as pool: rows=list(pool.map(lambda _:create(),range(6)))
    assert len({row['cliente']['id'] for row in rows})==1
    assert sum(row['creado'] for row in rows)==1


def test_correo_duplicado_y_nit_retail_no_se_modifican(system):
    payload=empresa()
    system.companies.post('/api/v1/clientes/corporativos',json=payload,headers=system.headers)
    response=system.companies.post('/api/v1/clientes/corporativos',json={**payload,'nit_ci':str(uuid4().int)[:12]},headers=system.headers)
    assert response.status_code==409
    retail=empresa()
    system.client.table('perfiles_clientes').insert({**retail,'nombre_completo':'Cliente particular','tipo_cliente':'retail'}).execute()
    response=system.companies.post('/api/v1/clientes/corporativos',json=retail,headers=system.headers)
    assert response.status_code==409
    assert system.client.table('perfiles_clientes').select('tipo_cliente').eq('nit_ci',retail['nit_ci']).execute().data[0]['tipo_cliente']=='retail'


@pytest.mark.parametrize('role',['cliente','cajero','authenticated'])
def test_empresas_y_parametros_exigen_rol_comercial(system,role):
    token=auth(role,user_metadata={'role':'administrador'})
    assert system.companies.post('/api/v1/clientes/corporativos',json=empresa(),headers=token).status_code==403
    assert system.quotes.get('/api/v1/cotizaciones/configuracion',headers=token).status_code==403


def test_configuracion_persistente_y_control_de_version(system):
    config=system.quotes.get('/api/v1/cotizaciones/configuracion',headers=system.headers)
    assert config.status_code==200 and config.headers['Cache-Control']=='no-store'
    new={'habilitado':True,'escalas':[{'minimo_unidades':3,'descuento_porcentaje':7.5}]}
    response=system.quotes.put('/api/v1/cotizaciones/configuracion',json={'version':1,'configuracion':new},headers=system.headers)
    assert response.status_code==200,response.text
    assert response.json()['version']==2
    assert system.quotes.put('/api/v1/cotizaciones/configuracion',json={'version':1,'configuracion':new},headers=system.headers).status_code==409
    assert system.quotes.get('/api/v1/cotizaciones/configuracion',headers=system.headers).json()['version']==2


@pytest.mark.parametrize('tiers',[
    [{'minimo_unidades':0,'descuento_porcentaje':5}],
    [{'minimo_unidades':2,'descuento_porcentaje':101}],
    [{'minimo_unidades':2,'descuento_porcentaje':5},{'minimo_unidades':2,'descuento_porcentaje':10}],
    [{'minimo_unidades':2,'descuento_porcentaje':10},{'minimo_unidades':5,'descuento_porcentaje':5}],
])
def test_escalas_invalidas_no_se_guardan(system,tiers):
    response=system.quotes.put('/api/v1/cotizaciones/configuracion',json={'version':1,'configuracion':{'habilitado':True,'escalas':tiers}},headers=system.headers)
    assert response.status_code==422,response.text
    assert system.quotes.get('/api/v1/cotizaciones/configuracion',headers=system.headers).json()['version']==1


def test_limites_y_descuentos_desactivados():
    config=ConfiguracionB2B(habilitado=True,escalas=[{'minimo_unidades':5,'descuento_porcentaje':7.5},{'minimo_unidades':10,'descuento_porcentaje':12}])
    assert [descuento_b2b(n,config) for n in [4,5,9,10,100]]==[0,Decimal('7.5'),Decimal('7.5'),12,12]
    config.habilitado=False
    assert descuento_b2b(100,config)==0
    assert descuento_b2b(100,ConfiguracionB2B(habilitado=True,escalas=[]))==0


def test_cotizar_usa_reglas_y_conserva_cotizaciones_emitidas(system):
    customer=system.companies.post('/api/v1/clientes/corporativos',json=empresa(),headers=system.headers).json()['cliente']['id']
    product,variant=str(uuid4()),str(uuid4())
    system.client.table('productos').insert({'id':product,'nombre':'Producto B2B','estado':'publicado'}).execute()
    system.client.table('variantes').insert({'id':variant,'producto_id':product,'sku':'SKU-B2B','precio':100}).execute()
    payload={'cliente_id':customer,'vigencia_dias':15,'items':[{'variante_id':variant,'cantidad':10}],'configuracion_descuento_version':1}
    first=system.quotes.post('/api/v1/cotizaciones',json=payload,headers=system.headers)
    assert first.status_code==201,first.text
    old=first.json()
    assert Decimal(str(old['total']))==900 and old['configuracion_descuento_version']==1
    config={'habilitado':True,'escalas':[{'minimo_unidades':10,'descuento_porcentaje':7.5}]}
    assert system.quotes.put('/api/v1/cotizaciones/configuracion',json={'version':1,'configuracion':config},headers=system.headers).status_code==200
    assert system.quotes.post('/api/v1/cotizaciones',json=payload,headers=system.headers).status_code==409
    second=system.quotes.post('/api/v1/cotizaciones',json={**payload,'configuracion_descuento_version':2},headers=system.headers)
    assert second.status_code==201,second.text
    assert Decimal(str(second.json()['total']))==925
    row=system.client.table('cotizaciones_b2b').select('*').eq('id',old['id']).execute().data[0]
    assert Decimal(str(row['total']))==900 and Decimal(str(row['descuento_porcentaje']))==10
    assert row['reglas_descuento']['escalas'][1]['descuento_porcentaje']=='10'
    row['created_at']='2026-11-10T03:56:59.78347+00:00'
    assert cotizaciones.cotizaciones_a_respuestas(system.client,[row])[0].total==900
    assert system.quotes.get('/api/v1/cotizaciones/'+old['id']+'/pdf',headers=system.headers).content.startswith(b'%PDF')


def test_objetos_b2b_no_estan_expuestos_a_roles_publicos(system):
    conn=system.connect()
    with conn.cursor() as cur:
        cur.execute("SELECT has_table_privilege('anon','cotizaciones_configuracion','SELECT'),has_function_privilege('authenticated','public.registrar_empresa_b2b(jsonb)','EXECUTE'),has_function_privilege('service_role','public.registrar_empresa_b2b(jsonb)','EXECUTE')")
        assert cur.fetchone()==(False,False,True)
    conn.close()
