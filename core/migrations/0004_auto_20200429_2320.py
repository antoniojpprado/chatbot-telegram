# Generated by Django 3.0.5 on 2020-04-29 23:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_auto_20200427_1258'),
    ]

    operations = [
        migrations.AddField(
            model_name='interaction',
            name='graph_style',
            field=models.TextField(db_column='graph_style', default='Informar', help_text='Style of the graph', verbose_name='Graph style'),
        ),
        migrations.AlterField(
            model_name='interaction',
            name='type',
            field=models.TextField(db_column='type', default='Column', help_text='Graph and Table interation type', verbose_name='Type of interation'),
        ),
    ]
